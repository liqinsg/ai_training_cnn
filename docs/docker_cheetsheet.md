# Start/stop/restart
docker compose up -d
docker compose down
docker compose restart

# Check status
docker ps
docker compose ps

# Watch live cron output
tail -f logs/fx_trade_bot_v7.log

# Force a manual run right now
docker exec fx-trade-bot python fx_trade_bot_v7.py --profile4

# View cron schedule inside container
docker exec fx-trade-bot cat /etc/cron.d/fx-bot

# Quick shell inside container for debugging
docker exec -it fx-trade-bot bash

# Check container logs (cron's own syslog — might show misses)
docker exec fx-trade-bot ls /var/log/    # cron often logs here
