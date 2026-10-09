#!/bin/bash
cd "$HOME/projects/ai_training_cnn"

# 加载环境变量
set -a
. .env
set +a

echo "===== $(date) — Attribution V2 Cron Start ====="

# 循环跑 4 个账号，每个独立日志
for prof in profile1 profile2 profile3 profile4; do
    echo "--- Running $prof ---"
    python -c "
import os
os.environ['ACTIVE_PROFILE'] = '$prof'
from attribution_v2.batch_backtest import main
main()
" >> logs/attribution_${prof}.log 2>&1
done

echo "===== Attribution V2 Cron Done ====="