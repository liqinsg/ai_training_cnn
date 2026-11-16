#!/usr/bin/env bash
# =============================================================================
# launch_fcv2_demo.sh — Phase 3.2 Feature Contract v2 (33 features) DEMO legs.
#
# Runs the trading bot against a SEPARATE FCV2 artifact set on the DEMO accounts
# only.  This script never passes --live, so the default trade_model_xgb.*
# (34 features, live) and the live leg are untouched.
#
#   FX_BOT_MODEL_STEM=models_fcv2/trade_model_xgb  → separate artifact quartet
#   OPT_USE_FEATURE_CONTRACT_V2=1                  → ml.feature_contract features
#
# Usage:  bash launch_fcv2_demo.sh [profile ...]        (default: 1 2 3 4)
# =============================================================================
set -u

PROJ="$HOME/projects/ai_training_cnn"
PY="/home/ubuntu/miniconda3/envs/ai-sprint/bin/python"
BOT="fx_trade_bot_v685.py"

PROFILES=("$@")
[ ${#PROFILES[@]} -eq 0 ] && PROFILES=(1 2 3 4)

cd "$PROJ" || exit 1
mkdir -p logs locks

export FX_BOT_MODEL_STEM="models_fcv2/trade_model_xgb"
export OPT_USE_FEATURE_CONTRACT_V2=1

pids=()
for P in "${PROFILES[@]}"; do
  name="fcv2_p${P}"
  log="logs/bot_${name}.log"
  (
    # per-profile lock: skip if a previous run is still active (prevents double orders)
    flock -n 9 || { echo "$(date -Is) [$name] previous run still active, skipped" >> "$log"; exit 0; }
    echo "$(date -Is) [$name] start: $PY $BOT -p $P (stem=$FX_BOT_MODEL_STEM FCV2=1)" >> "$log"
    exec "$PY" "$BOT" -p "$P"
  ) 9>"locks/${name}.lock" >> "$log" 2>&1 &
  pids+=($!)
done

rc=0
for p in "${pids[@]:-}"; do [ -n "$p" ] && { wait "$p" || rc=$?; }; done
exit $rc
