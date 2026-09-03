# Dockerfile for the AI training CNN application
# How to copy image to another server
# docker save ai-training-cnn:v20260903 | bzip2 | pv | ssh nie@10.240.26.196 'bunzip2 | docker load'
FROM --platform=linux/amd64 python:3.12-slim
# for Intel MacMini, must use amd64

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    gcc \
    g++ \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Install cron schedule
COPY fx-bot.cron /etc/cron.d/fx-bot
RUN chmod 0644 /etc/cron.d/fx-bot

# Create application directories
RUN mkdir -p /app/logs /app/state

# Run cron in foreground
CMD ["cron", "-f"]