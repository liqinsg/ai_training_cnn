#grep -E '^(SL_USE_HIERARCHICAL|SL_H4_LOOKBACK_BARS|SL_H8_LOOKBACK_BARS|SL_DAILY_LOOKBACK_BARS|SL_BUFFER_PIPS|SL_MIN_DISTANCE_PIPS|SL_FALLBACK_FIXED_PIPS)[[:space:]]*=' config_bot.py
#grep -E '^[[:space:]]*(SL_USE_HIERARCHICAL|SL_H4_LOOKBACK_BARS|SL_H8_LOOKBACK_BARS|SL_DAILY_LOOKBACK_BARS|SL_BUFFER_PIPS|SL_MIN_DISTANCE_PIPS|SL_FALLBACK_FIXED_PIPS)[[:space:]]*=' config_bot.py
#!/usr/bin/env sh
# usage: ./grep.sh v1,v2,v3 filename
# example: ./grep.sh SL_USE_HIERARCHICAL,SL_BUFFER_PIPS config_bot.py

set -eu

list_csv="${1:-}"
file="${2:-}"

if [ -z "$list_csv" ] || [ -z "$file" ]; then
  echo "usage: $0 v1,v2,v3 filename" >&2
  exit 1
fi

IFS=',' sh -c '
  set -eu
  IFS=','

  list_csv="$1"
  file="$2"

  # Build regex alternation: v1|v2|v3
  regex=""
  for v in $list_csv; do
    v_name=$(printf "%s" "$v" | tr -d "\r")
    if [ -z "$v_name" ]; then
      continue
    fi
    if [ -z "$regex" ]; then
      regex="$v_name"
    else
      regex="$regex|$v_name"
    fi
  done

  # Grep exact variable assignments (indented allowed)
  # Prints matching lines (variable = value), not partial matches.
  grep -E "^[[:space:]]*\\b($regex)\\b[[:space:]]*=" "$file"
' sh "$list_csv" "$file"
