#!/bin/sh
set -eu

DB_PATH="${MYTIMELOGGER_SQLITE_PATH:-/app/server/data/mtl_server.db}"
BACKUP_DIR="${MYTIMELOGGER_SQLITE_BACKUP_DIR:-/app/server/data/backups}"
LOCK_DIR="${BACKUP_DIR}/.sqlite-backup.lock"
export TZ=Asia/Shanghai

mkdir -p "$BACKUP_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "sqlite backup already running" >&2
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT HUP INT TERM

test -f "$DB_PATH"
stamp="$(date +%F-%H%M%S)"
final_path="${BACKUP_DIR}/app-${stamp}.db"
temp_path="${final_path}.tmp"
sqlite3 "$DB_PATH" ".backup '${temp_path}'"
test -s "$temp_path"
mv "$temp_path" "$final_path"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'app-*.db' -mtime +14 -delete
echo "sqlite backup completed: $final_path"
