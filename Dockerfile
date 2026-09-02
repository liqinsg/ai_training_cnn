FROM ai-training-cnn-base:v1

WORKDIR /app

COPY . .

COPY fx-bot.cron /etc/cron.d/fx-bot
RUN chmod 0644 /etc/cron.d/fx-bot

RUN mkdir -p /app/logs /app/state

CMD ["cron", "-f"]