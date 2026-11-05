param(
    [string]$NewHost,
    [string]$SourceHost,
    [string]$SnapshotPath,
    [string]$SshUser = 'root',
    [int]$SshPort = 22,
    [string]$RemoteDir = '/opt/mytimelogger',
    [int]$AppPort = 8000
)

$ErrorActionPreference = 'Stop'
$container = 'mytimelogger-sleep-server'
$imageTag = 'mytimelogger-migration:cutover'
$localImageTag = 'mytimelogger-server:latest'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$configPath = Join-Path $PSScriptRoot 'config.local.env'
$configText = [IO.File]::ReadAllText($configPath)
if (-not $NewHost) { $NewHost = Read-Host '新服务器 IP 或域名' }
if ($NewHost -notmatch '^[a-zA-Z0-9.-]+$') { throw "非法服务器地址: $NewHost" }
if ($SnapshotPath) { throw '菜单 [6] 现从当前服务器生成最新快照，不再接受旧的 -SnapshotPath' }
if ($SshUser -notmatch '^[a-zA-Z0-9_-]+$') { throw "非法 SSH 用户: $SshUser" }
if ($SshUser -ne 'root') { throw '简化迁移目前需要 root SSH 用户' }
if ($RemoteDir -notmatch '^/[a-zA-Z0-9/_-]+$') { throw '远端目录包含不允许的字符' }
$sourceMatch = [regex]::Match($configText, '(?m)^MTL_SERVER_HOST=([a-zA-Z0-9.-]+)\s*$')
if (-not $sourceMatch.Success) { throw 'config.local.env 中缺少有效的 MTL_SERVER_HOST' }
if ($SourceHost -and $SourceHost -ne $sourceMatch.Groups[1].Value) { throw '指定旧机与当前部署配置不一致；请先核对源服务器' }
$SourceHost = $sourceMatch.Groups[1].Value
if ($SourceHost -eq $NewHost) { throw '新旧服务器地址相同，停止迁移' }
$source = "${SshUser}@${SourceHost}"
$target = "${SshUser}@${NewHost}"
$identityPath = Join-Path $env:USERPROFILE '.ssh\mtl-migration-ed25519'
$runId = ([TimeZoneInfo]::ConvertTimeFromUtc([datetime]::UtcNow, [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time'))).ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
$stage = Join-Path $env:USERPROFILE "Desktop\mtl-migration\cutover-$runId"
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$imageFile = Join-Path $stage 'mtl-migration-image.tar'
$snapshotLocal = Join-Path $stage 'mtl_server_final.db'
$archiveLocal = Join-Path $stage 'server-files.tar'
$rcloneLocal = Join-Path $stage 'rclone'
$rcloneConfigLocal = Join-Path $stage 'rclone.conf'
$backupScriptLocal = Join-Path $stage 'backup_and_upload_sqlite.sh'

function Initialize-MigrationKey {
    $keyDir = Split-Path -Parent $identityPath
    New-Item -ItemType Directory -Force -Path $keyDir | Out-Null
    if (-not (Test-Path -LiteralPath $identityPath)) {
        $keygen = New-Object System.Diagnostics.ProcessStartInfo
        $keygen.FileName = (Get-Command ssh-keygen).Source
        $keygen.Arguments = '-q -t ed25519 -N "" -f "' + $identityPath + '"'
        $keygen.UseShellExecute = $false
        $keygen.CreateNoWindow = $true
        $process = [System.Diagnostics.Process]::Start($keygen)
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) { throw '创建迁移专用 SSH 密钥失败' }
    }
    if (-not (Test-Path -LiteralPath "$identityPath.pub")) { throw '迁移公钥文件缺失' }
}
function Test-KeyAccess([string]$server) {
    $probe = New-Object System.Diagnostics.ProcessStartInfo
    $probe.FileName = (Get-Command ssh).Source
    $probe.Arguments = '-q -i "' + $identityPath + '" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 -p ' + $SshPort + ' ' + $server + ' true'
    $probe.UseShellExecute = $false
    $probe.CreateNoWindow = $true
    $probe.RedirectStandardError = $true
    $probe.RedirectStandardOutput = $true
    $process = [System.Diagnostics.Process]::Start($probe)
    try { $process.WaitForExit(); return ($process.ExitCode -eq 0) }
    finally { $process.Dispose() }
}
function Ensure-KeyAccess([string]$server, [string]$label) {
    if (Test-KeyAccess $server) { return }
    Write-Host "请为$label $server 输入一次 SSH 密码；输错会立即停止。" -ForegroundColor Cyan
    $pub = ((Get-Content -LiteralPath "$identityPath.pub" -Raw).Trim() -split '\s+')[0..1] -join ' '
    if ($pub -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+$') { throw '迁移公钥格式无效' }
    & ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -p $SshPort $server "umask 077; mkdir -p /root/.ssh; chmod 700 /root/.ssh; touch /root/.ssh/authorized_keys; echo >> /root/.ssh/authorized_keys; echo '$pub' >> /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys"
    if ($LASTEXITCODE -ne 0) { throw "$label $server 密码错误或 SSH 登录失败；请核对后重新选择菜单 [6]" }
    if (-not (Test-KeyAccess $server)) { throw "$label $server 公钥认证失败；请检查远端 authorized_keys 权限" }
}
function Invoke-Remote([string]$server, [string]$command) {
    $result = & ssh -i $identityPath -o IdentitiesOnly=yes -o BatchMode=yes -p $SshPort $server $command
    if ($LASTEXITCODE -ne 0) { throw "SSH 失败: $server / $command" }
    return ($result -join "`n").Trim()
}
function Invoke-BinaryTransfer([string]$mode, [string]$server, [string]$remoteFile, [string]$localFile) {
    $pythonCode = @'
import subprocess, sys
mode, ssh, key, port, server, remote, local = sys.argv[1:]
command = [ssh, '-T', '-i', key, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=30', '-p', port, server, ('cat > ' if mode == 'upload' else 'cat ') + remote]
with open(local, 'rb' if mode == 'upload' else 'wb') as stream:
    result = subprocess.run(command, stdin=stream if mode == 'upload' else None, stdout=stream if mode == 'download' else None)
sys.exit(result.returncode)
'@
    & python -c $pythonCode $mode (Get-Command ssh).Source $identityPath $SshPort $server $remoteFile $localFile
    if ($LASTEXITCODE -ne 0) { throw "SSH 二进制传输失败：$mode ${server}:$remoteFile" }
}
function Assert-RemoteSpace([string]$server, [string]$directory, [long]$bytes) {
    $report = Invoke-Remote $server "df -Pk $directory"
    $columns = (($report -split "`n")[-1].Trim() -split '\s+')
    [long]$availableKb = 0
    if ($columns.Count -lt 4 -or -not [long]::TryParse($columns[3], [ref]$availableKb)) { throw "无法读取 $server 的剩余磁盘空间: $report" }
    if ($availableKb * 1024 -lt $bytes + 33554432) { throw "$server 的 $directory 剩余空间不足，至少需要 $([math]::Ceiling(($bytes + 33554432) / 1MB)) MB" }
}
function Copy-FromRemote([string]$server, [string]$remoteFile, [string]$localFile) {
    $partialFile = "$localFile.partial"
    Write-Host "下载 ${server}:$remoteFile"
    Invoke-BinaryTransfer 'download' $server $remoteFile $partialFile
    Move-Item -LiteralPath $partialFile -Destination $localFile -Force
}
function Copy-ToRemote([string]$localFile, [string]$server, [string]$remoteFile) {
    $inputFile = Get-Item -LiteralPath $localFile
    $remoteDirectory = $remoteFile -replace '/[^/]+$', ''
    Assert-RemoteSpace $server $remoteDirectory $inputFile.Length
    Write-Host "上传 $($inputFile.Name) 到 $server（$([math]::Ceiling($inputFile.Length / 1MB)) MB）"
    Invoke-BinaryTransfer 'upload' $server $remoteFile $localFile
}
function Assert-RemoteFileHash([string]$server, [string]$remoteFile, [string]$localFile) {
    $localHash = (Get-FileHash -LiteralPath $localFile -Algorithm SHA256).Hash.ToLowerInvariant()
    $remoteHash = (Invoke-Remote $server "sha256sum $remoteFile").Split(' ')[0].ToLowerInvariant()
    if ($localHash -ne $remoteHash) { throw "文件哈希不一致：${server}:$remoteFile" }
}
function Assert-EmptyTarget([string]$server, [string]$image) {
    $fileCount = Invoke-Remote $server "find ${RemoteDir}/attachments ${RemoteDir}/reports -type f -print -quit 2>/dev/null | wc -l"
    if ([int]$fileCount -ne 0) { throw '新机已有附件或报告，拒绝覆盖' }
    $hasDb = Invoke-Remote $server "if test -s ${RemoteDir}/data/mtl_server.db; then echo yes; else echo no; fi"
    if ($hasDb -eq 'yes') {
        $counts = Invoke-Remote $server "docker run --rm -v ${RemoteDir}/data:/app/server/data $image sqlite3 /app/server/data/mtl_server.db 'SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM server_change_log; SELECT COUNT(*) FROM server_study_sessions;'"
        if ($counts -ne "0`n0`n0") { throw '新机已有用户或业务数据，拒绝覆盖' }
    }
}
function Check-Db([string]$path) {
    $result = & python -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0]); c.close()" $path
    if ($LASTEXITCODE -ne 0 -or $result.Count -lt 2 -or $result[0] -ne 'ok') { throw '本机 SQLite 完整性检查失败' }
    $count = [int]$result[1]
    if ($count -lt 1) { throw '本机数据库为空，停止迁移' }
    return $count
}

function Start-Migration {
$sourceStopped = $false
$targetStarted = $false
$configUpdated = $false
$targetPredeployed = $false
$targetPredeployedStopped = $false
try {
    Write-Host "迁移脚本：$PSCommandPath（当前旧机 -> 新机完整切换）"
    Write-Host "旧机 $SourceHost -> 新机 $NewHost；本机暂存 $stage"
    Initialize-MigrationKey
    Ensure-KeyAccess $source '旧服务器'
    Ensure-KeyAccess $target '新服务器'
    $sourceRunning = Invoke-Remote $source "docker inspect --format '{{.State.Running}}' $container"
    if ($sourceRunning -ne 'true') { throw '旧机容器未运行，停止迁移' }
    $sourceImage = Invoke-Remote $source "docker inspect --format '{{.Image}}' $container"
    $sourceMounts = (Invoke-Remote $source "docker inspect --format '{{json .Mounts}}' $container") | ConvertFrom-Json
    $dataMount = @($sourceMounts | Where-Object { $_.Destination -eq '/app/server/data' -and $_.Source -eq "$RemoteDir/data" })
    if ($dataMount.Count -ne 1) { throw '旧机数据挂载与迁移目录不一致，停止迁移' }
    Invoke-Remote $source "docker run --rm $sourceImage test -x /app/server/scripts/backup_sqlite.sh && test -s ${RemoteDir}/data/mtl_server.db && echo ready" | Out-Null
    $rclonePath = Invoke-Remote $source 'command -v rclone'
    if ($rclonePath -notmatch '^/[a-zA-Z0-9/_-]+$') { throw '旧机 rclone 路径无效' }
    Invoke-Remote $source "test -s /root/.config/rclone/rclone.conf && test -f ${RemoteDir}/backup_and_upload_sqlite.sh && echo ready" | Out-Null
    Invoke-Remote $target "docker version --format '{{.Server.Version}}'" | Out-Null
    Invoke-Remote $target 'command -v crontab && command -v tar && command -v sha256sum' | Out-Null
    $targetContainer = Invoke-Remote $target "docker ps -aq --filter name=^/${container}`$"
    if ($targetContainer) {
        $targetPredeployed = $true
        $targetPredeployedWasRunning = (Invoke-Remote $target "docker inspect --format '{{.State.Running}}' $container") -eq 'true'
        $predeployedImage = Invoke-Remote $target "docker inspect --format '{{.Image}}' $container"
        $targetMounts = (Invoke-Remote $target "docker inspect --format '{{json .Mounts}}' $container") | ConvertFrom-Json
        foreach ($name in @('data', 'attachments', 'reports')) {
            $destination = if ($name -eq 'reports') { '/app/reports' } else { "/app/server/$name" }
            if (@($targetMounts | Where-Object { $_.Destination -eq $destination -and $_.Source -eq "$RemoteDir/$name" }).Count -ne 1) { throw "新机容器 $name 挂载不符合预期，拒绝接管" }
        }
        Assert-EmptyTarget $target $predeployedImage
    } else {
        $targetOccupied = Invoke-Remote $target "if test -s ${RemoteDir}/data/mtl_server.db || find ${RemoteDir}/attachments ${RemoteDir}/reports -type f -print -quit 2>/dev/null | grep -q .; then echo occupied; else echo empty; fi"
        if ($targetOccupied -ne 'empty') { throw '新机已有数据库或附件，停止以免覆盖' }
    }
    & docker build -t $localImageTag -f (Join-Path $projectRoot 'server\Dockerfile') $projectRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw '本地服务端镜像构建失败' }
    $localRuntime = & docker image inspect --format '{{json .RootFS.Layers}}|{{json .Config.Cmd}}|{{json .Config.Env}}' $localImageTag
    if ($LASTEXITCODE -ne 0) { throw '无法读取本地构建镜像' }
    $localRuntime = ($localRuntime -join "`n").Trim()
    $matchingImage = $null
    $targetImages = Invoke-Remote $target "docker image ls --no-trunc --format '{{.ID}}'"
    foreach ($candidate in ($targetImages -split "`n" | Select-Object -Unique)) {
        if (-not $candidate) { continue }
        if ((Invoke-Remote $target "docker image inspect --format '{{json .RootFS.Layers}}|{{json .Config.Cmd}}|{{json .Config.Env}}' $candidate") -eq $localRuntime) {
            $matchingImage = $candidate
            break
        }
    }
    if ($matchingImage) {
        Write-Host '新机已有与当前代码一致的镜像，直接复用。'
        Invoke-Remote $target "docker tag $matchingImage $imageTag" | Out-Null
    } else {
        Write-Host '上传本机构建的服务端镜像...'
        & docker save -o $imageFile $localImageTag
        if ($LASTEXITCODE -ne 0) { throw '本地镜像导出失败' }
        Copy-ToRemote $imageFile $target '/root/mtl-migration-image.tar'
        Invoke-Remote $target 'docker load -i /root/mtl-migration-image.tar' | Out-Host
        Invoke-Remote $target "docker tag $localImageTag $imageTag" | Out-Null
    }
    $targetRuntime = Invoke-Remote $target "docker image inspect --format '{{json .RootFS.Layers}}|{{json .Config.Cmd}}|{{json .Config.Env}}' $imageTag"
    if ($localRuntime -ne $targetRuntime) { throw '新机镜像与本机构建不一致，停止迁移' }
    Invoke-Remote $target "mkdir -p ${RemoteDir}/data ${RemoteDir}/attachments ${RemoteDir}/reports ${RemoteDir}/log" | Out-Null
    Assert-EmptyTarget $target $imageTag
    if (-not $targetPredeployed) { Invoke-Remote $target "docker run --rm -p ${AppPort}:8000 $imageTag true" | Out-Null }

    Copy-FromRemote $source $rclonePath $rcloneLocal
    Copy-FromRemote $source '/root/.config/rclone/rclone.conf' $rcloneConfigLocal
    Copy-FromRemote $source "$RemoteDir/backup_and_upload_sqlite.sh" $backupScriptLocal
    if ($targetPredeployed) {
        $targetPredeployedStopped = $true
        if ($targetPredeployedWasRunning) { Invoke-Remote $target "docker stop $container" | Out-Null }
        Assert-EmptyTarget $target $predeployedImage
    }
    Write-Host '停止旧机写入并生成最终 SQLite 快照...' -ForegroundColor Cyan
    $sourceStopped = $true
    Invoke-Remote $source "docker stop $container" | Out-Null
    $backupOutput = Invoke-Remote $source "docker run --rm -e MYTIMELOGGER_SQLITE_BACKUP_DIR=/app/server/data/migration-backups -v ${RemoteDir}/data:/app/server/data $sourceImage /app/server/scripts/backup_sqlite.sh"
    $backupName = [regex]::Match($backupOutput, 'app-\d{4}-\d{2}-\d{2}-\d{6}\.db').Value
    if (-not $backupName) { throw "旧机最终快照路径无法识别: $backupOutput" }
    $remoteSnapshot = "$RemoteDir/data/migration-backups/$backupName"
    Copy-FromRemote $source $remoteSnapshot $snapshotLocal
    $objectCount = Check-Db $snapshotLocal
    $localHash = (Get-FileHash -LiteralPath $snapshotLocal -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "旧机最终快照检查通过：$objectCount 个数据库对象，SHA256=$localHash"
    $remoteArchive = "/root/mtl-server-files-$runId.tar"
    $sourceManifest = Invoke-Remote $source "cd $RemoteDir && find attachments reports -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum"
    Invoke-Remote $source "tar -C $RemoteDir -cf $remoteArchive attachments reports" | Out-Null
    $sourceArchiveHash = (Invoke-Remote $source "sha256sum $remoteArchive").Split(' ')[0].ToLowerInvariant()
    Copy-FromRemote $source $remoteArchive $archiveLocal
    if ((Get-FileHash -LiteralPath $archiveLocal -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceArchiveHash) { throw '旧机附件归档下载哈希不一致' }
    Copy-ToRemote $archiveLocal $target $remoteArchive
    if ((Invoke-Remote $target "sha256sum $remoteArchive").Split(' ')[0].ToLowerInvariant() -ne $sourceArchiveHash) { throw '新机附件归档上传哈希不一致' }

    Copy-ToRemote $snapshotLocal $target "$RemoteDir/data/mtl_server.migrating.db"
    $check = Invoke-Remote $target "docker run --rm -v ${RemoteDir}/data:/app/server/data $imageTag sqlite3 /app/server/data/mtl_server.migrating.db 'PRAGMA integrity_check; SELECT COUNT(*) FROM sqlite_master;'"
    if ($check -ne "ok`n$objectCount") { throw "新机数据库检查失败: $check" }
    $remoteHash = (Invoke-Remote $target "sha256sum ${RemoteDir}/data/mtl_server.migrating.db").Split(' ')[0].ToLowerInvariant()
    if ($localHash -ne $remoteHash) { throw '新机数据库 SHA256 不匹配' }
    Invoke-Remote $target "tar -C $RemoteDir -xf $remoteArchive" | Out-Null
    $targetManifest = Invoke-Remote $target "cd $RemoteDir && find attachments reports -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum"
    if ($sourceManifest -ne $targetManifest) { throw '新机附件/报告逐文件 SHA256 不一致' }
    Invoke-Remote $target "for suffix in '' -wal -shm; do if test -e ${RemoteDir}/data/mtl_server.db`$suffix; then if test -e ${RemoteDir}/data/mtl_server.empty-pre-migration.db`$suffix; then exit 1; fi; mv ${RemoteDir}/data/mtl_server.db`$suffix ${RemoteDir}/data/mtl_server.empty-pre-migration.db`$suffix; fi; done; mv ${RemoteDir}/data/mtl_server.migrating.db ${RemoteDir}/data/mtl_server.db" | Out-Null

    if ($targetPredeployed) { Invoke-Remote $target "docker rm $container" | Out-Null }
    $run = "docker run -d --name $container --restart unless-stopped -e MYTIMELOGGER_SERVER_MODE=1 -e MYTIMELOGGER_ENVIRONMENT=testing -e SERVER_RUNTIME_OVERWRITE=1 -e SERVER_SLEEP_DB_PATH=/app/server/data/mtl_server.db -p ${AppPort}:8000 -v ${RemoteDir}/data:/app/server/data -v ${RemoteDir}/attachments:/app/server/attachments -v ${RemoteDir}/reports:/app/reports -v ${RemoteDir}/log:/app/server/log $imageTag"
    $targetStarted = $true
    Invoke-Remote $target $run | Out-Host
    $healthy = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri "http://${NewHost}:${AppPort}/ping" -UseBasicParsing -TimeoutSec 4
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch { }
    }
    if (-not $healthy) { throw '新机 HTTP /ping 未通过；请检查新机容器日志' }
    $expectedCounts = & python -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); print(c.execute('SELECT COUNT(*) FROM users').fetchone()[0]); print(c.execute('SELECT COUNT(*) FROM server_study_sessions').fetchone()[0]); c.close()" $snapshotLocal
    if ($LASTEXITCODE -ne 0 -or $expectedCounts.Count -ne 2) { throw '无法读取源库核心表数量' }
    $actualCounts = Invoke-Remote $target "docker exec $container sqlite3 /app/server/data/mtl_server.db 'SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM server_study_sessions;'"
    if ($actualCounts -ne ($expectedCounts -join "`n")) { throw "新机核心表数量不符：源=$($expectedCounts -join ',') 新=$actualCounts" }
    Invoke-Remote $target 'mkdir -p /root/.config/rclone /usr/local/bin && chmod 700 /root/.config/rclone' | Out-Null
    Copy-ToRemote $rcloneLocal $target '/usr/local/bin/rclone.mtl-migrating'
    Assert-RemoteFileHash $target '/usr/local/bin/rclone.mtl-migrating' $rcloneLocal
    Copy-ToRemote $rcloneConfigLocal $target '/root/.config/rclone/rclone.conf.mtl-migrating'
    Invoke-Remote $target 'chmod 600 /root/.config/rclone/rclone.conf.mtl-migrating' | Out-Null
    Assert-RemoteFileHash $target '/root/.config/rclone/rclone.conf.mtl-migrating' $rcloneConfigLocal
    Copy-ToRemote $backupScriptLocal $target "$RemoteDir/backup_and_upload_sqlite.sh.mtl-migrating"
    Assert-RemoteFileHash $target "$RemoteDir/backup_and_upload_sqlite.sh.mtl-migrating" $backupScriptLocal
    Invoke-Remote $target "mv /usr/local/bin/rclone.mtl-migrating /usr/local/bin/rclone && chmod 755 /usr/local/bin/rclone && mv /root/.config/rclone/rclone.conf.mtl-migrating /root/.config/rclone/rclone.conf && chmod 600 /root/.config/rclone/rclone.conf && mv ${RemoteDir}/backup_and_upload_sqlite.sh.mtl-migrating ${RemoteDir}/backup_and_upload_sqlite.sh && chmod 755 ${RemoteDir}/backup_and_upload_sqlite.sh" | Out-Null
    Invoke-Remote $target 'rclone version' | Select-Object -First 1 | Out-Host
    $cronScript = Join-Path $PSScriptRoot 'install-migration-cron.sh'
    Copy-ToRemote $cronScript $target "$RemoteDir/install-migration-cron.sh"
    Assert-RemoteFileHash $target "$RemoteDir/install-migration-cron.sh" $cronScript
    Invoke-Remote $target "REMOTE_DIR=$RemoteDir CONTAINER_NAME=$container sh ${RemoteDir}/install-migration-cron.sh" | Out-Host
    $backupCheck = Invoke-Remote $target "REMOTE_DIR=$RemoteDir CONTAINER_NAME=$container BACKUP_RUN_SOURCE=migration ${RemoteDir}/backup_and_upload_sqlite.sh"
    if ($backupCheck -notmatch 'stage=s3_verify result=ok') { throw '新机 S3 备份未验证成功' }
    $updated = [regex]::Replace($configText, '(?m)^MTL_SERVER_HOST=[^\r\n]+(?=\r?$)', "MTL_SERVER_HOST=$NewHost")
    if ($updated -eq $configText) { throw '本机部署地址未更新，迁移未完成' }
    [IO.File]::WriteAllText($configPath, $updated, [Text.UTF8Encoding]::new($false))
    $configUpdated = $true
    Write-Host "迁移成功：数据库、附件、报告、S3 备份均已验证；客户端服务地址改为 http://${NewHost}:${AppPort}" -ForegroundColor Green
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($sourceStopped -and -not $configUpdated) {
        if ($targetStarted) {
            try { Invoke-Remote $target "docker stop $container" | Out-Null; Write-Warning '新机容器已停止，避免双端同时写入。' }
            catch { Write-Warning "新机容器停止失败：$($_.Exception.Message)" }
        }
        try {
            Invoke-Remote $source "docker start $container" | Out-Null
            if ((Invoke-Remote $source "docker inspect --format '{{.State.Running}}' $container") -ne 'true') { throw '旧机容器未运行' }
            Write-Warning '旧机服务已恢复，部署地址仍指旧机。'
        } catch { Write-Warning "旧机服务自动恢复失败：$($_.Exception.Message)；请立即人工检查。" }
    }
    if ($targetPredeployedStopped -and -not $sourceStopped -and -not $targetStarted -and $targetPredeployedWasRunning) {
        try { Invoke-Remote $target "docker start $container" | Out-Null; Write-Warning '新机原空容器已恢复。' }
        catch { Write-Warning "新机原容器恢复失败：$($_.Exception.Message)" }
    }
    Write-Warning "迁移未完成；本机暂存目录保留：$stage"
    throw
} finally {
    if (Test-Path -LiteralPath $rcloneConfigLocal) { Remove-Item -LiteralPath $rcloneConfigLocal -Force }
}
}

if ($MyInvocation.InvocationName -ne '.') { Start-Migration }
