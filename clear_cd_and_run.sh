#!/bin/bash
# 用法：bash clear_cd_and_run.sh [profile-number]
# 示例：bash clear_cd_and_run.sh 4

PROFILE=${1:-4}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

echo "════════════════════════════════════════"
echo "🧹 清除 Profile${PROFILE} 冷却文件..."
# cooldown state is per (profile, environment): DEMO and LIVE each own a file.
# The bare `cooldown_profile${PROFILE}.json` is the pre-isolation legacy name —
# remove it too so no stale file lingers.
rm -f "cooldown_profile${PROFILE}_demo.json" \
      "cooldown_profile${PROFILE}_live.json" \
      "cooldown_profile${PROFILE}.json"
echo "✅ 已清除 cooldown_profile${PROFILE}_{demo,live}.json (含旧名)"

echo ""
echo "🏃 运行 Profile${PROFILE}..."
echo "════════════════════════════════════════"
# FCV2 model env MUST match crontab, otherwise this run silently falls back to
# the legacy 34-feature model and audits a different code path than production.
cd "$SCRIPT_DIR" && \
FX_BOT_MODEL_STEM=models_fcv2/trade_model_xgb OPT_USE_FEATURE_CONTRACT_V2=1 \
/home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v685.py -p ${PROFILE} --max-entries 10

echo ""
echo "════════════════════════════════════════"
echo "🔍 查找 G 分数输出："
echo "  关键词：G= / TREND_G / Final score"
echo "════════════════════════════════════════"
