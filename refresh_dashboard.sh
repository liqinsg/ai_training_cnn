#!/bin/bash
# Attribution V2 — Refresh Dashboard
# 统一入口：先聚合数据 → 再生成报告
set -euo pipefail

# 工作目录
PROJECT_DIR="$HOME/projects/ai_training_cnn"
cd "$PROJECT_DIR" || exit 1

# 环境
PY_BIN="/home/ubuntu/miniconda3/envs/ai-sprint/bin/python"
LOG_FILE="$PROJECT_DIR/logs/attribution_cron.log"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') — Start Dashboard Refresh ====="

# Step 1: 聚合 4-Profile 最新数据
echo "→ Running batch_backtest..."
"$PY_BIN" attribution_v2/batch_backtest.py >> "$LOG_FILE" 2>&1

# Step 2: 生成可视化 + HTML 报告
echo "→ Running visualizer..."
"$PY_BIN" attribution_v2/visualizer.py >> "$LOG_FILE" 2>&1

echo "✅ Done — Dashboard Updated"
echo
