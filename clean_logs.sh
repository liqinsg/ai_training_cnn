#!/usr/bin/env bash
# Remove zero-size files from logs/ (and its subdirectories).
# Usage: ./clean_logs.sh [-n]   (-n = dry run, only list what would be deleted)
set -euo pipefail

LOG_DIR="$(cd "$(dirname "$0")" && pwd)/logs"
DRY_RUN=0
[ "${1:-}" = "-n" ] && DRY_RUN=1

if [ ! -d "$LOG_DIR" ]; then
    echo "Directory not found: $LOG_DIR" >&2
    exit 1
fi

count=0
while IFS= read -r -d '' f; do
    echo "$f"
    if [ "$DRY_RUN" -eq 0 ]; then
        rm -f -- "$f"
    fi
    count=$((count + 1))
done < <(find "$LOG_DIR" -type f -size 0 -print0)

if [ "$count" -eq 0 ]; then
    echo "No zero-size files found in $LOG_DIR"
elif [ "$DRY_RUN" -eq 1 ]; then
    echo "Dry run: $count zero-size file(s) would be deleted from $LOG_DIR"
else
    echo "Deleted $count zero-size file(s) from $LOG_DIR"
fi