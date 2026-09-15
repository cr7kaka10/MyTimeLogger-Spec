#!/bin/sh
set -eu

REMOTE_DIR="${REMOTE_DIR:-/opt/mytimelogger}"
CONTAINER_NAME="${CONTAINER_NAME:-mytimelogger-sleep-server}"
IMAGE_NAME="${IMAGE_NAME:-mytimelogger-server}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_PORT="${APP_PORT:-8000}"
ENVIRONMENT="${ENVIRONMENT:-testing}"

mkdir -p "$REMOTE_DIR/data" "$REMOTE_DIR/attachments" "$REMOTE_DIR/reports" "$REMOTE_DIR/log"
cd "$REMOTE_DIR"
chmod +x "$REMOTE_DIR/backup_and_upload_sqlite.sh"

echo ">>> Loading Docker image..."
docker load -i mytimelogger-server.tar

echo ">>> Stopping old container if present..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

echo ">>> Starting new container..."
container_id="$(docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -e MYTIMELOGGER_SERVER_MODE=1 \
    -e MYTIMELOGGER_ENVIRONMENT="$ENVIRONMENT" \
    -e SERVER_RUNTIME_OVERWRITE=1 \
    -e SERVER_SLEEP_DB_PATH=/app/server/data/mtl_server.db \
    -p "$APP_PORT":8000 \
    -v "$REMOTE_DIR/data":/app/server/data \
    -v "$REMOTE_DIR/attachments":/app/server/attachments \
    -v "$REMOTE_DIR/reports":/app/reports \
    -v "$REMOTE_DIR/log":/app/server/log \
    "$IMAGE_NAME:$IMAGE_TAG")"
echo ">>> Container ID: $container_id"

echo ">>> Waiting for service startup..."
sleep 5

container_state="$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME")"
echo ">>> Container status: $container_state"
docker ps --filter "name=$CONTAINER_NAME" --format 'table {{.Status}}\t{{.Ports}}'

echo ">>> Recent container logs:"
docker logs --tail 80 "$CONTAINER_NAME" || true

if [ "$container_state" != "running" ]; then
    echo ">>> Container is not running. Deploy failed."
    exit 1
fi

cron_file="$(mktemp)"
crontab -l 2>/dev/null | grep -v -e 'mytimelogger-sqlite-backup' -e '^CRON_TZ=Asia/Shanghai$' > "$cron_file" || true
printf '%s\n' 'CRON_TZ=Asia/Shanghai' >> "$cron_file"
printf '%s\n' "0 3 * * * REMOTE_DIR=$REMOTE_DIR CONTAINER_NAME=$CONTAINER_NAME BACKUP_RUN_SOURCE=cron $REMOTE_DIR/backup_and_upload_sqlite.sh # mytimelogger-sqlite-backup" >> "$cron_file"
crontab "$cron_file"
rm -f "$cron_file"
echo ">>> SQLite backup scheduled daily at 03:00 Asia/Shanghai"
crontab -l | grep 'mytimelogger-sqlite-backup'
