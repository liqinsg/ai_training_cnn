#!/bin/bash
# 批量更新所有账户
LIVE=(
    "7 001-003-21515688-001"
    "7 001-003-21515688-002"
)
DEMO=(
    "7 101-003-39389016-001"
    "7 101-003-39389016-002"
)

echo "=== FX DAILY UPDATE $(date '+%Y-%m-%d %H:%M') ==="
for acc in "${LIVE[@]}"; do
    python fx_daily_report.py $acc
done
for acc in "${DEMO[@]}"; do
    python fx_daily_report.py $acc
done
echo "=== 全部完成 ==="
