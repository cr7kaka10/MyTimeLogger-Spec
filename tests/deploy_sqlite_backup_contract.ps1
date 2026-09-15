$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dockerfile = Get-Content (Join-Path $root 'server\Dockerfile') -Raw
$script = Get-Content (Join-Path $root 'server\scripts\backup_sqlite.sh') -Raw
$remote = Get-Content (Join-Path $root 'deploy\remote_deploy.sh') -Raw
$powershell = Get-Content (Join-Path $root 'deploy\deploy-server.ps1') -Raw
$batch = Get-Content (Join-Path $root 'deploy\deploy-test.bat') -Raw
$wrapper = Get-Content (Join-Path $root 'deploy\backup_and_upload_sqlite.sh') -Raw

if ($dockerfile -notmatch 'sqlite3') { throw 'Docker image must include sqlite3 CLI' }
foreach ($term in @('.backup', 'Asia/Shanghai', 'sqlite-backup.lock', '.tmp', '-mtime +14')) {
    if ($script -notmatch [regex]::Escape($term)) { throw "backup script missing: $term" }
}
if ($remote -notmatch 'backup_and_upload_sqlite\.sh') {
    throw 'Test-server deployment does not install or schedule the backup-and-upload wrapper.'
}
if ($remote -notmatch '0 3 \* \* \* REMOTE_DIR=' -or $remote -notmatch 'CRON_TZ=Asia/Shanghai' -or $remote -notmatch 'mytimelogger-sqlite-backup') {
    throw 'Test-server deployment must register the Beijing 03:00 backup-and-upload cron.'
}
if ($powershell -notmatch '0 3 \* \* \* docker exec' -or $powershell -notmatch 'CRON_TZ=Asia/Shanghai' -or $powershell -notmatch 'mytimelogger-sqlite-backup') {
    throw 'PowerShell deployment local-only SQLite backup cron is missing.'
}
foreach ($term in @('rclone copyto', 'rclone lsf', 'PRAGMA integrity_check', 's3:obss3/mytimelogger/testing/sqlite')) {
    if ($wrapper -notmatch [regex]::Escape($term)) { throw "backup-and-upload wrapper missing: $term" }
}
if ($wrapper -match '--include|--exclude') {
    throw 'S3 verification must not add rclone include/exclude filters.'
}
foreach ($term in @('rclone lsf --files-only', 'grep -Fx', 'LOG_FILE=', 'BACKUP_RUN_SOURCE:-manual', 'source=%s')) {
    if ($wrapper -notmatch [regex]::Escape($term)) { throw "reliable backup wrapper missing: $term" }
}
if ($remote -notmatch 'BACKUP_RUN_SOURCE=cron' -or $remote -match 'sqlite-backup\.log 2>&1') {
    throw 'Cron must identify its source and leave logging to the wrapper.'
}
foreach ($term in @('Backup test server database now', ':do_backup_server', 'backup_and_upload_sqlite.sh')) {
    if ($batch -notmatch [regex]::Escape($term)) { throw "test-server menu contract missing: $term" }
}
if ($batch -notmatch 'BACKUP_RUN_SOURCE=manual') {
    throw 'Manual backup must identify its source for the persistent log.'
}
Write-Host 'SQLite backup deployment contract passed'
