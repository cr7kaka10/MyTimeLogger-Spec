#!/bin/sh
set -eu

REMOTE_DIR="${REMOTE_DIR:-/opt/mytimelogger}"
CONTAINER_NAME="${CONTAINER_NAME:-mytimelogger-sleep-server}"
BACKUP_DIR="$REMOTE_DIR/data/backups"
LOG_FILE="$REMOTE_DIR/log/sqlite-backup.log"
S3_DIR="${MTL_SQLITE_BACKUP_S3_DIR:-s3:obss3/mytimelogger/testing/sqlite}"
RUN_SOURCE="${BACKUP_RUN_SOURCE:-manual}"

log() {
  printf '%s source=%s %s\n' "$(TZ=Asia/Shanghai date '+%F %T')" "$RUN_SOURCE" "$*" | tee -a "$LOG_FILE"
}

fail() {
  log "stage=$1 result=failed"
  exit 1
}

mkdir -p "$(dirname "$LOG_FILE")"
log 'stage=backup result=started'
command -v rclone >/dev/null || fail rclone_unavailable

if ! output="$(docker exec "$CONTAINER_NAME" /app/server/scripts/backup_sqlite.sh 2>&1)"; then
  log "$output"
  fail sqlite_backup
fi
log "$output"
snapshot="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'app-*.db' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"
test -n "$snapshot" || fail snapshot_missing
filename="$(basename "$snapshot")"
integrity="$(docker exec "$CONTAINER_NAME" sqlite3 "/app/server/data/backups/$filename" 'PRAGMA integrity_check;')" || fail integrity_check
test "$integrity" = "ok" || fail integrity_check
log "stage=integrity result=ok snapshot=$filename"
rclone copyto "$snapshot" "$S3_DIR/$filename" || fail s3_upload
log "stage=s3_upload result=ok remote=$S3_DIR/$filename"
listing="$(rclone lsf --files-only "$S3_DIR")" || fail s3_verify_list
printf '%s\n' "$listing" | grep -Fx "$filename" >/dev/null || fail s3_verify_object
log "stage=s3_verify result=ok remote=$S3_DIR/$filename integrity=$integrity"
