FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MYTIMELOGGER_SERVER_MODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    sqlite3 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from zoneinfo import ZoneInfo; assert ZoneInfo('Asia/Shanghai').key == 'Asia/Shanghai'"

COPY server ./server
COPY shared ./shared

RUN chmod +x /app/server/scripts/backup_sqlite.sh

RUN mkdir -p /app/server/data /app/server/attachments /app/server/log /app/reports

EXPOSE 8000

CMD ["uvicorn", "server.server:app", "--host", "0.0.0.0", "--port", "8000"]
