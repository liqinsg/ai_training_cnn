#!/bin/bash
# Auto-retrain model → run bot → check positions
# Schedule: e.g. daily at 00:00 / every 4 hours

cd /home/nie/projects/ai_training_cnn || exit 1

LOG_FILE="/home/nie/projects/ai_training_cnn/bot_cron.log"

echo "===== START: $(date) =====" >> "$LOG_FILE"

# 1. Retrain model (fresh data)
echo "→ Retraining model..." >> "$LOG_FILE"
python retrain_model.py >> "$LOG_FILE" 2>&1

# 2. Run trading bot
echo "→ Running bot..." >> "$LOG_FILE"
python fx_trade_bot_integrated_v6.5.py --timeframe 15m --no-test-trade >> "$LOG_FILE" 2>&1

# 3. Check & log positions
echo "→ Checking positions..." >> "$LOG_FILE"
python check_order_details.py >> "$LOG_FILE" 2>&1

echo "===== END: $(date) =====" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
