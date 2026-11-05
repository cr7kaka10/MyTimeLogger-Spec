$ErrorActionPreference = 'Stop'
$root = Join-Path $env:TEMP ('mtl-migration-test-' + [guid]::NewGuid().ToString('N'))
$deploy = Join-Path $root 'deploy'
$originalProfile = $env:USERPROFILE
$env:USERPROFILE = $root
New-Item -ItemType Directory -Path $deploy | Out-Null
Copy-Item (Join-Path $PSScriptRoot '..\migrate-server.ps1') (Join-Path $deploy 'migrate-server.ps1')
[IO.File]::WriteAllText((Join-Path $deploy 'config.local.env'), "MTL_SERVER_HOST=192.0.2.1`r`n")
try {
    . (Join-Path $deploy 'migrate-server.ps1') -NewHost '192.0.2.2'
    $stage = Join-Path $root 'stage'
    New-Item -ItemType Directory -Path $stage | Out-Null
    $snapshotLocal = Join-Path $stage 'mtl_server_final.db'
    $archiveLocal = Join-Path $stage 'server-files.tar'
    $rcloneLocal = Join-Path $stage 'rclone'
    $rcloneConfigLocal = Join-Path $stage 'rclone.conf'
    $backupScriptLocal = Join-Path $stage 'backup_and_upload_sqlite.sh'
    $archiveBytes = [Text.Encoding]::UTF8.GetBytes('archive')
    $archiveHash = ([BitConverter]::ToString(([Security.Cryptography.SHA256]::Create()).ComputeHash($archiveBytes))).Replace('-', '').ToLowerInvariant()
    function Initialize-MigrationKey { }
    function Ensure-KeyAccess { }
    function Check-Db { 270 }
    function Assert-RemoteFileHash { }
    function Copy-ToRemote { }
    function Copy-FromRemote([string]$server, [string]$remoteFile, [string]$localFile) {
        if ($script:scenario -eq 'transfer' -and $localFile -eq $snapshotLocal) { throw 'simulated transfer failure' }
        $value = if ($localFile -eq $archiveLocal) { 'archive' } else { 'snapshot' }
        [IO.File]::WriteAllText($localFile, $value)
    }
    function docker {
        $global:LASTEXITCODE = 0
        if (($args -join ' ') -like '*image inspect*') { 'runtime' }
    }
    function python { $global:LASTEXITCODE = 0; '2'; '47' }
    function Start-Sleep { }
    function Invoke-WebRequest { [pscustomobject]@{ StatusCode = 200 } }
    function Invoke-Remote([string]$server, [string]$command) {
        if ($server -eq $source -and $command -like 'docker stop*') { $script:sourceWasStopped = $true; return 'stopped' }
        if ($server -eq $source -and $command -like 'docker start*') { $script:sourceWasRestarted = $true; return 'started' }
        if ($server -eq $target -and $command -like 'docker run -d*') { $script:targetWasStarted = $true; return 'container-id' }
        if ($server -eq $target -and $command -like 'docker stop*') { $script:targetWasStopped = $true; return 'stopped' }
        if ($command -like '*State.Running*') { return 'true' }
        if ($command -like '*json .Mounts*') { return '[{"Destination":"/app/server/data","Source":"/opt/mytimelogger/data"},{"Destination":"/app/server/attachments","Source":"/opt/mytimelogger/attachments"},{"Destination":"/app/reports","Source":"/opt/mytimelogger/reports"}]' }
        if ($command -like '*docker inspect*Image*') { return 'sha256:old' }
        if ($command -like 'command -v rclone*') { return '/usr/local/bin/rclone' }
        if ($command -like '*docker ps -aq*') { if ($script:scenario -eq 'predeployed') { return 'container-id' }; return '' }
        if ($command -like '*occupied; else echo empty*') { if ($script:scenario -eq 'occupied') { return 'occupied' }; return 'empty' }
        if ($command -like '*docker image ls*') { return 'sha256:built' }
        if ($command -like '*docker image inspect*') { return 'runtime' }
        if ($command -like '*wc -l*') { return '0' }
        if ($command -like '*then echo yes; else echo no*') { if ($script:scenario -eq 'predeployed') { return 'yes' }; return 'no' }
        if ($command -like '*server_change_log*') { return "0`n0`n0" }
        if ($command -like '*sqlite backup completed*') { return 'sqlite backup completed: /app/server/data/migration-backups/app-2026-11-05-120000.db' }
        if ($command -like '*backup_sqlite.sh' -and $command -like '*MYTIMELOGGER_SQLITE_BACKUP_DIR*') { return 'sqlite backup completed: /app/server/data/migration-backups/app-2026-11-05-120000.db' }
        if ($command -like '*sha256sum*server-files*') { return "$archiveHash  file" }
        if ($command -like '*sha256sum*mtl_server.migrating.db*') { return "$((Get-FileHash $snapshotLocal -Algorithm SHA256).Hash.ToLowerInvariant())  file" }
        if ($command -like '*find attachments reports -type f -print0*') { return 'abc  attachments/one.jpg' }
        if ($command -like '*PRAGMA integrity_check*') { return "ok`n270" }
        if ($command -like '*SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM server_study_sessions*') { return "2`n47" }
        if ($command -like '*rclone version*') { return 'rclone v1' }
        if ($command -like '*BACKUP_RUN_SOURCE=migration*') { if ($script:scenario -eq 'backup') { return 'stage=s3_verify result=failed' }; return 'stage=s3_verify result=ok' }
        return 'ready'
    }
    foreach ($case in @('success', 'predeployed', 'occupied', 'transfer', 'backup')) {
        $script:scenario = $case
        $script:sourceWasStopped = $false
        $script:sourceWasRestarted = $false
        $script:targetWasStarted = $false
        $script:targetWasStopped = $false
        [IO.File]::WriteAllText($configPath, "MTL_SERVER_HOST=192.0.2.1`r`n")
        $failed = $false
        try { Start-Migration } catch { $failed = $true }
        $hostNow = [IO.File]::ReadAllText($configPath)
        if ($case -eq 'success' -and ($failed -or $hostNow -notmatch '192.0.2.2' -or -not $script:sourceWasStopped -or -not $script:targetWasStarted)) { throw "success scenario failed: failed=$failed host=$hostNow oldStopped=$script:sourceWasStopped targetStarted=$script:targetWasStarted" }
        if ($case -eq 'predeployed' -and ($failed -or -not $script:targetWasStopped -or -not $script:targetWasStarted -or $hostNow -notmatch '192.0.2.2')) { throw 'predeployed scenario failed' }
        if ($case -eq 'occupied' -and (-not $failed -or $script:sourceWasStopped -or $hostNow -notmatch '192.0.2.1')) { throw 'occupied target scenario failed' }
        if ($case -eq 'transfer' -and (-not $failed -or -not $script:sourceWasStopped -or -not $script:sourceWasRestarted -or $hostNow -notmatch '192.0.2.1')) { throw 'transfer recovery scenario failed' }
        if ($case -eq 'backup' -and (-not $failed -or -not $script:sourceWasRestarted -or -not $script:targetWasStopped -or $hostNow -notmatch '192.0.2.1')) { throw 'backup recovery scenario failed' }
        Write-Host "PASS $case"
    }
} finally {
    $env:USERPROFILE = $originalProfile
    Remove-Item -LiteralPath $root -Recurse -Force
}
