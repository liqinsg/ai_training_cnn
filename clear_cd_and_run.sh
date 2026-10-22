#!/bin/bash
# 用法：bash clear_cd_and_run.sh [profile-number]
# 示例：bash clear_cd_and_run.sh 4

PROFILE=${1:-4}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

echo "════════════════════════════════════════"
echo "🧹 清除 Profile${PROFILE} 冷却文件..."
rm -f cooldown_profile${PROFILE}.json
echo "✅ 已清除 cooldown_profile${PROFILE}.json"

echo ""
echo "🏃 运行 Profile${PROFILE}..."
echo "════════════════════════════════════════"
/home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v685_2.py -p ${PROFILE} --max-entries 10

echo ""
echo "════════════════════════════════════════"
echo "🔍 查找 G 分数输出："
echo "  关键词：G= / TREND_G / Final score"
echo "════════════════════════════════════════"
