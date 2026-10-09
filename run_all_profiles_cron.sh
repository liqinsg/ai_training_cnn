#!/bin/bash
cd /home/qili/projects/ai_training_cnn
set -a; [ -f .env ] && . .env; set +a

echo "===== $(date '+%Y-%m-%d %H:%M:%S') — Attribution V2 Cron ====="

# 1. 拉最新代码（测试服务器）
git pull origin v2026

# 2. 补历史数据（新文件自动处理）
python apply_patch_to_history.py

# 3. 跑4套完整回测
python attribution_v2/batch_backtest.py

# 4. 生成图表 + HTML报告
python attribution_v2/visualizer.py

echo "===== Done ====="
echo "📊 Open: attribution_v2/reports/latest.html"