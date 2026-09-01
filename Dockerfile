FROM python:3.12-slim

WORKDIR /app

# Install only what is needed for cron
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install cron schedule
COPY fx-bot.cron /etc/cron.d/fx-bot
RUN chmod 0644 /etc/cron.d/fx-bot

# Create application directories
RUN mkdir -p /app/logs /app/state

# Run cron in foreground
CMD ["cron", "-f"]