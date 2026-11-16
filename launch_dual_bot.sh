#!/usr/bin/env bash
# =============================================================================
# launch_dual_bot.sh — 同时启动同一个 profile 的 DEMO 与 LIVE 两条腿。
#
# 目的：两条腿跑的是同一套策略/同一个 profile，唯一区别是执行环境，
#       以便逐行对比 demo 与 live 的日志（信号、评分、ML 概率应一致）。
#
#     demo 腿 :  -p <PROFILE>
#     live 腿 :  -p <PROFILE> --live --lots <LOTS>
#
# 所有参数都原样透传给 fx_trade_bot_v685.py —— 参数列表与 bot 的 argparse
# 完全一致，脚本本身不拼造任何 bot 不认识的参数。
#
# 用法:  bash launch_dual_bot.sh [PROFILE] [LOTS]
#     PROFILE  profile 号 1/2/3/4   (默认 3)
#     LOTS     live 腿手数           (默认 1)
#   例:  bash launch_dual_bot.sh 2 1  ->  demo: -p 2
#                                        live: -p 2 --live --lots 1
#
# 环境变量可覆盖: ENABLE_DEMO=0 ENABLE_LIVE=0 DRY_RUN=1
# =============================================================================
set -u

PROJ="$HOME/projects/ai_training_cnn"
PY="/home/ubuntu/miniconda3/envs/ai-sprint/bin/python"
BOT="fx_trade_bot_v685.py"

# --- 两条腿唯一的差异点 ---
PROFILE="${1:-3}"     # 两条腿共用同一个 profile
LOTS="${2:-1}"        # 仅 live 腿使用

# 让两条腿都跑 crontab 在用的同一套 33 特征 FCV2 工件，保证与线上是同一条
# 模型路径（可按需用环境变量覆盖）。
export FX_BOT_MODEL_STEM="${FX_BOT_MODEL_STEM:-models_fcv2/trade_model_xgb}"
export OPT_USE_FEATURE_CONTRACT_V2="${OPT_USE_FEATURE_CONTRACT_V2:-1}"

# --- switches (override via env) ---
ENABLE_DEMO="${ENABLE_DEMO:-1}"
ENABLE_LIVE="${ENABLE_LIVE:-1}"
DRY_RUN="${DRY_RUN:-0}"            # 1 = print commands only
KILL_FILE="$PROJ/STOP_LIVE"        # touch this file to block live instantly

cd "$PROJ" || exit 1
mkdir -p logs locks

pids=()
launch_leg() {  # usage: launch_leg <name> <logfile> <bot args...>
  local name=$1 log=$2; shift 2
  if [ "$DRY_RUN" = 1 ]; then
    echo "[dry-run] $name: $PY $BOT $*  >> $log"; return
  fi
  (
    # per-leg lock: skip if previous run is still going (prevents double orders)
    flock -n 9 || { echo "$(date -Is) [$name] previous run still active, skipped" >> "$log"; exit 0; }
    echo "$(date -Is) [$name] start: $PY $BOT $*" >> "$log"
    exec "$PY" "$BOT" "$@"
  ) 9>"locks/$name.lock" >> "$log" 2>&1 &
  pids+=($!)
}

# ── 两条腿：profile 相同，仅环境/手数不同 ────────────────────────────────────
#    demo : -p <PROFILE>
#    live : -p <PROFILE> --live --lots <LOTS>
[ "$ENABLE_DEMO" = 1 ] && \
  launch_leg "demo_p${PROFILE}" "logs/bot_profile${PROFILE}_C.log" \
             -p "$PROFILE"
if [ "$ENABLE_LIVE" = 1 ] && [ ! -e "$KILL_FILE" ]; then
  launch_leg "live_p${PROFILE}" "logs/bot_profile${PROFILE}_Clive.log" \
             -p "$PROFILE" --live --lots "$LOTS"
fi

rc=0
for p in "${pids[@]:-}"; do [ -n "$p" ] && { wait "$p" || rc=$?; }; done
exit $rc
