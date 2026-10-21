#!/bin/bash
# 每日一键更新脚本 — 按需填入你的4个Profile查询参数
# 使用: bash fx_daily_update.sh

# ========== 配置你的4个账户 ==========
# 格式: "查询天数|Profile备注名"
ACCOUNTS_LIVE=(
    "7|001-003-21515688-001"
    "7|001-003-21515688-002"
    "7|001-003-21515688-003"
    "7|001-003-21515688-004"
)
ACCOUNTS_DEMO=(
    "7|101-003-39389016-001"
    "7|101-003-39389016-002"
    "7|101-003-39389016-003"
    "7|101-003-39389016-004"
)

# ====================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  FX Daily Update — $(date '+%Y-%m-%d %H:%M')"
echo "======================================"

for acc in "${ACCOUNTS[@]}"; do
    IFS='|' read -r days name <<< "$acc"
    echo -e "\n📥 更新: $name (查询最近$days天)"
    python fx_trade_closed_status.py "$days" | python fx_trade_to_csv.py "$days"
done

echo -e "\n📊 生成汇总报告"
python fx_daily_report.py

echo -e "\n✅ 全部完成！CSV位置: $SCRIPT_DIR/trade_data/"
ls -lh trade_data/*.csv 2>/dev/null
