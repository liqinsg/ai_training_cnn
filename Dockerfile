FROM python:3.12-slim

WORKDIR /app

# Install system deps:
#   cron                 — the scheduler
#   libta-lib-dev        — C library needed by Python TA-Lib package
#   build-essential      — in case pip needs to compile TA-Lib from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    libta-lib-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy your existing requirement files and merge them (no new file needed)
COPY requirements.txt ./
RUN cat requirements.txt | sort -u | grep -v '^#' | grep -v '^'

# Copy project code
COPY . .

# Copy crontab entry (separate file is cleaner than echo inside RUN)
COPY fx-bot.cron /etc/cron.d/fx-bot
RUN chmod 0644 /etc/cron.d/fx-bot

# Make sure logs dir exists
RUN mkdir -p /app/logs /app/state

# Run cron in foreground
CMD ["cron", "-f"] > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt requirements.txt 

# Copy project code
COPY . .

# Copy crontab entry (separate file is cleaner than echo inside RUN)
COPY fx-bot.cron /etc/cron.d/fx-bot
RUN chmod 0644 /etc/cron.d/fx-bot

# Make sure logs dir exists
RUN mkdir -p /app/logs /app/state

# Run cron in foreground
CMD ["cron", "-f"]