#!/bin/sh
set -eu

REMOTE_DIR="${REMOTE_DIR:-/opt/mytimelogger}"
CONTAINER_NAME="${CONTAINER_NAME:-mytimelogger-sleep-server}"
cron_file="$(mktemp)"
trap 'rm -f "$cron_file"' EXIT HUP INT TERM

crontab -l 2>/dev/null | grep -v -e 'mytimelogger-sqlite-backup' -e '^CRON_TZ=Asia/Shanghai$' > "$cron_file" || true
printf '%s\n' 'CRON_TZ=Asia/Shanghai' >> "$cron_file"
printf '%s\n' "0 3 * * * REMOTE_DIR=$REMOTE_DIR CONTAINER_NAME=$CONTAINER_NAME BACKUP_RUN_SOURCE=cron $REMOTE_DIR/backup_and_upload_sqlite.sh # mytimelogger-sqlite-backup" >> "$cron_file"
crontab "$cron_file"
crontab -l | grep -F 'mytimelogger-sqlite-backup'
