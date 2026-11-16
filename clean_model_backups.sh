#!/usr/bin/env bash
# clean_model_backups.sh — prune timestamped model snapshots (*_bak_<YYYYMMDD_HHMM>).
#
# Keeps only the newest N backups per artifact type, deletes the rest.
# Types covered (root stem `trade_model_xgb` and `scaler`):
#   trade_model_xgb_bak_*.json
#   trade_model_xgb.features_bak_*.json
#   trade_model_xgb.cfg_bak_*.json
#   scaler_bak_*.joblib
#   trade_model_xgb_bak_*.pkl
#
# Timestamps are %Y%m%d_%H%M, so a lexicographic sort == chronological order.
#
# Usage:
#   ./clean_model_backups.sh                 # prune ./ (keep 3)
#   ./clean_model_backups.sh --dry-run       # show what would be deleted
#   ./clean_model_backups.sh --keep 5        # keep newest 5 per type
#   ./clean_model_backups.sh --keep 3 models_fcv2
set -euo pipefail

DRY=0
KEEP=3
DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    -n|--dry-run) DRY=1 ;;
    --keep)       KEEP="${2:?--keep needs a number}"; shift ;;
    -h|--help)
      sed -n '2,22p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *)  DIR="$1" ;;
  esac
  shift
done

if [ -z "$DIR" ]; then
  DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
cd "$DIR"

shopt -s nullglob

PATTERNS=(
  "trade_model_xgb_bak_*.json"
  "trade_model_xgb.features_bak_*.json"
  "trade_model_xgb.cfg_bak_*.json"
  "scaler_bak_*.joblib"
  "trade_model_xgb_bak_*.pkl"
)

echo "dir : $DIR"
echo "keep: newest $KEEP per type   dry-run: $DRY"
echo "--------------------------------------------------------------"

total=0
for pat in "${PATTERNS[@]}"; do
  files=( $pat )                     # nullglob -> empty if no match
  n=${#files[@]}
  if [ "$n" -le "$KEEP" ]; then
    printf '%-38s have=%-3d delete=0\n' "$pat" "$n"
    continue
  fi

  # sort ascending (oldest first); everything before the last KEEP is obsolete
  mapfile -t sorted < <(printf '%s\n' "${files[@]}" | sort)
  ndel=$(( n - KEEP ))
  printf '%-38s have=%-3d delete=%d\n' "$pat" "$n" "$ndel"

  for ((i = 0; i < ndel; i++)); do
    f="${sorted[$i]}"
    if [ "$DRY" = 1 ]; then
      echo "  [dry-run] rm -- $f"
    else
      rm -f -- "$f" && echo "  rm -- $f"
    fi
    total=$(( total + 1 ))
  done
done

echo "--------------------------------------------------------------"
if [ "$DRY" = 1 ]; then
  echo "dry-run: would delete $total file(s)"
else
  echo "done: deleted $total file(s)"
fi
