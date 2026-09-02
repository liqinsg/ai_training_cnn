FROM --platform=linux/amd64 python:3.12-slim
# for Intel MacMini, must use amd64

WORKDIR /app

# 装cron + 编译依赖 + 调试工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    gcc \
    g++ \
    procps \     # 加ps top
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code  <--- 修好了
COPY . .

# Install cron schedule
COPY fx-bot.cron /etc/cron.d/fx-bot
RUN chmod 0644 /etc/cron.d/fx-bot
# Create application directories
RUN mkdir -p /app/logs /app/state

# Run cron in foreground
CMD ["cron", "-f"]