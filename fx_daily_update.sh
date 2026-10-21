#!/bin/bash
# 每日一键更新 — 适配当前文件结构
# 用法: bash fx_daily_update.sh

# ========== 账户配置 ==========
LIVE=(
    "7|001-003-21515688-001"
    "7|001-003-21515688-002"
    "7|001-003-21515688-003"
    "7|001-003-21515688-004"
)
DEMO=(
    "7|101-003-39389016-001"
    "7|101-003-39389016-002"
    "7|101-003-39389016-003"
    "7|101-003-39389016-004"
)
# ==============================

set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  FX DAILY UPDATE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

update_group() {
    local label="$1"
    local -n arr="$2"
    echo -e "\n$label"
    for acc in "${arr[@]}"; do
        IFS='|' read -r days pid <<< "$acc"
        echo -n "  $pid ... "
        python fx_trade_closed_status.py "$days" "$pid" | python fx_save_to_csv.py "$days" "$pid"
    done
}

update_group "🔴 更新实盘账户" LIVE
update_group "🟢 更新模拟账户" DEMO

echo -e "\n📊 生成汇总报告"
python fx_daily_report.py

echo -e "\n✅ 全部完成！CSV: ./trade_data/"
ls -lh trade_data/*.csv 2>/dev/null
