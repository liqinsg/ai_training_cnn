#!/usr/bin/env bash
# =============================================================================
# launch_dual_bot.sh — 同时启动同一个 profile 的 DEMO 与 LIVE 两条腿。
#
# 完整说明（参数、环境变量、两条腿的命令、日志路径、kill-switch、退出码）
# 以 --help 为唯一来源，直接查看:
#     bash launch_dual_bot.sh --help
# =============================================================================
set -u

usage() {
  cat <<'EOF'
launch_dual_bot.sh — 同时启动同一个 profile 的 DEMO 与 LIVE 两条腿

目的:
  两条腿跑同一套策略、同一个 profile，唯一区别是执行环境与手数，
  便于逐行对比 demo 与 live 的日志（信号/评分/ML 概率应一致）。

用法:
  bash launch_dual_bot.sh [PROFILE] [LOTS]
  bash launch_dual_bot.sh -h | --help        显示本帮助

参数:
  PROFILE   profile 号 1/2/3/4               (默认 3)
  LOTS      live 腿手数                       (默认 1)

两条腿（参数原样透传给 fx_trade_bot_v685.py）:
  demo : holiday filter → fx_trade_bot_v685.py -p <PROFILE>
  live : holiday filter → fx_trade_bot_v685.py -p <PROFILE> --live --lots <LOTS>

运行方式与输出（重要）:
  · 两条腿都在后台运行；脚本会一直等待它们结束才返回。
  · 终端不再打印运行日志——全部输出（stdout+stderr）写入日志文件，
    终端只打印日志路径。
  · 日志文件（固定命名，暂不可改）:
        demo : logs/bot_profile<P>_C.log
        live : logs/bot_profile<P>_Clive.log
  · 实时查看:  tail -f logs/bot_profile<P>_C.log logs/bot_profile<P>_Clive.log
  · 排错:      tail -n 100 logs/bot_profile<P>_Clive.log

环境变量:
  ENABLE_DEMO=0/1   是否启动 demo 腿                      (默认 1)
  ENABLE_LIVE=0/1   是否启动 live 腿（另受 STOP_LIVE 限制） (默认 1)
  DRY_RUN=1         仅打印将执行的命令，不真正启动         (默认 0)
  FX_BOT_MODEL_STEM           模型工件前缀 (默认 models_fcv2/trade_model_xgb)
  OPT_USE_FEATURE_CONTRACT_V2 启用 33 特征契约             (默认 1)

kill-switch / 文件约定:
  STOP_LIVE        项目根目录下存在该文件 → 立即跳过 live 腿。
                   启动: touch STOP_LIVE      解除: rm STOP_LIVE
  locks/<leg>.lock 每条腿一个 flock 锁；若上一次仍在此运行，该腿被跳过，
                   并在其日志写入 "previous run still active, skipped"
                   （防止重复下单）。
  logs/  locks/    脚本启动时自动创建。

固定路径:
  工作目录  : $HOME/projects/ai_training_cnn
  解释器    : /home/ubuntu/miniconda3/envs/ai-sprint/bin/python
  被调脚本  : fx_trade_bot_v685.py

退出码:
  0        正常结束（或 --help）
  2        参数非法（PROFILE 不是 1/2/3/4）
  其它     某条腿的退出码（脚本等待两条腿后返回）

示例:
  bash launch_dual_bot.sh 2 1     # demo: -p 2 ; live: -p 2 --live --lots 1
  DRY_RUN=1 bash launch_dual_bot.sh 2 2
  ENABLE_LIVE=0 bash launch_dual_bot.sh 3
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

PROJ="$HOME/projects/ai_training_cnn"
PY="/home/ubuntu/miniconda3/envs/ai-sprint/bin/python"
BOT="fx_trade_bot_v685.py"

# --- 两条腿唯一的差异点 ---
PROFILE="${1:-3}"     # 两条腿共用同一个 profile
LOTS="${2:-1}"        # 仅 live 腿使用

case "$PROFILE" in
  1|2|3|4) ;;
  *)
    echo "ERROR: PROFILE 必须是 1/2/3/4（收到 '$PROFILE'）" >&2
    echo "       用法见: bash launch_dual_bot.sh --help" >&2
    exit 2
    ;;
esac

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
    echo "[dry-run] $name: $PY scripts/oanda_holiday_launcher.py -- $PY $BOT $*  >> $log"; return
  fi
  (
    # per-leg lock: skip if previous run is still going (prevents double orders)
    flock -n 9 || { echo "$(date -Is) [$name] previous run still active, skipped" >> "$log"; exit 0; }
    echo "$(date -Is) [$name] start: $PY $BOT $*" >> "$log"
    exec "$PY" scripts/oanda_holiday_launcher.py -- "$PY" "$BOT" "$@"
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

# ── 终端提示：输出都在日志文件里，这里只打印路径 + 查看方式 ──────────────────
DEMO_LOG="logs/bot_profile${PROFILE}_C.log"
LIVE_LOG="logs/bot_profile${PROFILE}_Clive.log"
echo "── launch_dual_bot.sh (profile=${PROFILE}, lots=${LOTS}) ──"
[ "$ENABLE_DEMO" = 1 ]      && echo "  demo : $DEMO_LOG"
if [ "$ENABLE_LIVE" = 1 ] && [ ! -e "$KILL_FILE" ]; then
  echo "  live : $LIVE_LOG"
elif [ -e "$KILL_FILE" ]; then
  echo "  live : 已跳过（存在 $KILL_FILE）"
fi
if [ "$DRY_RUN" != 1 ]; then
  echo "  实时查看: tail -f $DEMO_LOG $LIVE_LOG"
  echo "  排错示例: tail -n 50 $LIVE_LOG      # 看 live 腿最后 50 行"
fi
echo "───────────────────────────────────────────────"

rc=0
for p in "${pids[@]:-}"; do [ -n "$p" ] && { wait "$p" || rc=$?; }; done
exit $rc
