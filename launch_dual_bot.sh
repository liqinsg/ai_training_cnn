#!/usr/bin/env bash
# Launch demo + live bot legs at the same instant (same args, same start time)
set -u

PROJ="$HOME/projects/ai_training_cnn"
PY="/home/ubuntu/miniconda3/envs/ai-sprint/bin/python"
BOT="fx_trade_bot_v685.py"

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
    exec "$PY" "$BOT" "$@"
  ) 9>"locks/$name.lock" >> "$log" 2>&1 &
  pids+=($!)
}

[ "$ENABLE_DEMO" = 1 ] && launch_leg demo logs/bot_profile3_C.log     -p 3
if [ "$ENABLE_LIVE" = 1 ] && [ ! -e "$KILL_FILE" ]; then
  launch_leg live logs/bot_profile3_Clive.log -p 3 --live -a 3
fi

rc=0
for p in "${pids[@]:-}"; do [ -n "$p" ] && { wait "$p" || rc=$?; }; done
exit $rc
