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

# Copy crontab entry (separate file is cleaner than echo inside RUN)
COPY fx-bot.cron /etc/cron.d/fx-bot
RUN chmod 0644 /etc/cron.d/fx-bot

# Make sure logs dir exists
RUN mkdir -p /app/logs /app/state

# Run cron in foreground
CMD ["cron", "-f"]