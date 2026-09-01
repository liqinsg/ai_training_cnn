FROM python:3.12-slim

WORKDIR /app

# Install system deps: cron (scheduler), ta-lib C lib, git (optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    libatlas-base-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy consolidated requirements (create this file from requirementx*.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Create crontab: run every 15 min at 0,15,30,45
echo '0/15 * * * * root cd /app && /usr/local/bin/python /app/fx_trade_bot_v7.py --profile4 >> /app/logs/fx_trade_bot_v7.log 2>&1' > /etc/cron.d/fx-bot
# Fix crontab perms (required by cron)
RUN chmod 0644 /etc/cron.d/fx-bot

# Make sure logs dir exists
RUN mkdir -p /app/logs /app/state

# Run cron in foreground
CMD ["cron", "-f"]