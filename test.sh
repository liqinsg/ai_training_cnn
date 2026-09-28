#!/usr/bin/env bash
# ─── FX BOT ENV 验证脚本 ───
# 用法: bash test_env.sh

cd "$(dirname "$0")"

echo "================================================================="
echo "  FX BOT — 环境变量 + dotenv 自动加载 验证"
echo "================================================================="
echo ""

# ─── 1. 干净 shell 状态 ───
echo "【1】Shell 原生 env（source 之前）"
echo "  OANDA vars: $(env | grep -i '^OANDA' | wc -l) 个（预期 0）"
echo ""

# ─── 2. .env + run.env 内容检查 ───
echo "【2】.env / run.env 文件内容"
echo "  .env  LIVE token      : $(grep -c 'OANDA_API_TOKEN_LIVE' .env | xargs -I{} echo '{} 行')"
echo "  .env  1_LIVE account  : $(grep 'OANDA_ACCOUNT_ID_1_LIVE' .env | grep -v '^#' | sed 's/.*=//' | tr -d '"')"
echo "  run.env DEFAULT_LOT   : $(grep 'DEFAULT_LOT_SIZE' run.env | grep -v '^#' | sed 's/.*=//' | tr -d '"')"
echo "  run.env DRY_RUN       : $(grep 'DRY_RUN' run.env | grep -v '^#' | sed 's/.*=//' | tr -d '"')"
echo ""

# ─── 3. Python dotenv 自动加载（关键！不 source shell） ───
echo "【3】Python dotenv 自动加载（不 source shell）"
python3 << 'PYEOF'
from config_oanda import (
    OANDA_API_TOKEN_DEMO, OANDA_API_TOKEN_LIVE,
    OANDA_ACCOUNT_ID_DEMO_1, OANDA_ACCOUNT_ID_1_LIVE,
)
import os

checks = [
    (OANDA_API_TOKEN_DEMO,     "DEMO token"),
    (OANDA_API_TOKEN_LIVE,     "LIVE token"),
    (OANDA_ACCOUNT_ID_DEMO_1,  "DEMO account 1"),
    (OANDA_ACCOUNT_ID_1_LIVE,  "LIVE account 1"),
    (os.getenv("DEFAULT_LOT_SIZE", ""), "run.env LOT"),
    (os.getenv("DRY_RUN", ""),  "run.env DRY_RUN (默认空)"),
]

all_ok = True
for v, label in checks:
    if label == "run.env DRY_RUN (默认空)" and not v:
        mark = "OK (not set)"
    elif v:
        mark = f"OK ({v if 'TOKEN' not in label else 'len='+str(len(v))})"
    else:
        mark = "MISSING ❌"
        all_ok = False
    print(f"  {label:<22s} {mark}")
print()
print(f"  dotenv 加载: {'✅ PASS' if all_ok else '❌ FAIL'}")
PYEOF
echo ""

# ─── 4. config_oanda.py import 测试 ───
echo "【4】config_oanda.py import + LIVE profile 构建"
python3 << 'PYEOF' 2>&1 | tail -20
from config_oanda import get_oanda_profile, OANDA_API_TOKEN_LIVE, OANDA_ACCOUNT_ID_1_LIVE
errors = []
if not OANDA_API_TOKEN_LIVE:
    errors.append("LIVE token 为空！检查 .env")
if "101-003" not in OANDA_ACCOUNT_ID_1_LIVE:
    errors.append(f"LIVE account ID 前缀不对: {OANDA_ACCOUNT_ID_1_LIVE}")

for live_flag in (False, True):
    ctx = get_oanda_profile(profile_num="3", env_override="live" if live_flag else None)
    mode = "--live" if live_flag else "(demo)"
    print(f"  -p 3 {mode:>7s}  →  env={ctx['env']:8s}  account={ctx['account_id']}")
    if live_flag and ctx["account_id"] != OANDA_ACCOUNT_ID_1_LIVE:
        errors.append(f"LIVE 应该走 account 001，实际走了 {ctx['account_id']}")

if errors:
    print()
    for e in errors:
        print(f"  ❌ {e}")
else:
    print()
    print("  ✅ 全部通过")
PYEOF
echo ""

# ─── 5. fx_trade_bot_v71.py AST ───
echo "【5】fx_trade_bot_v71.py 语法检查"
python3 -c "import ast; ast.parse(open('fx_trade_bot_v71.py').read()); print('  ✅ AST OK')"
python3 -c "import ast; ast.parse(open('config_oanda.py').read()); print('  ✅ AST OK')"
echo ""

# ─── 6. 关键行为 grep ───
echo "【6】关键代码路径检查"
echo -n "  DRY_RUN = args.dry_run or os.getenv  : "
grep -c 'DRY_RUN = args.dry_run or os.getenv' fx_trade_bot_v71.py | xargs -I{} echo "{} 处"
echo -n "  DEFAULT_LOT_SIZE os.getenv 优先      : "
grep -c 'DEFAULT_LOT_SIZE = int(os.getenv' fx_trade_bot_v71.py | xargs -I{} echo "{} 处"
echo -n "  max(1, int(DEFAULT_LOT_SIZE * mult))  : "
grep -c 'max(1, int(DEFAULT_LOT_SIZE' fx_trade_bot_v71.py | xargs -I{} echo "{} 处"
echo -n "  args.dry_run 残留 (除定义处)          : "
grep -n 'args.dry_run' fx_trade_bot_v71.py | grep -v 'DRY_RUN = args' | wc -l | xargs -I{} echo "{} 处 (应为 0)"
echo ""
echo "================================================================="
echo "  完成"
echo "================================================================="