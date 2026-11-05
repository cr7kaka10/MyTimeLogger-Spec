param(
    [string]$NewHost,
    [string]$SourceHost,
    [string]$SshUser = 'root',
    [int]$SshPort = 22,
    [string]$RemoteDir = '/opt/mytimelogger',
    [int]$AppPort = 8000
)

$ErrorActionPreference = 'Stop'
$container = 'mytimelogger-sleep-server'
$imageTag = 'mytimelogger-migration:cutover'
$configPath = Join-Path $PSScriptRoot 'config.local.env'
$configText = [IO.File]::ReadAllText($configPath)
if (-not $SourceHost) {
    $match = [regex]::Match($configText, '(?m)^MTL_SERVER_HOST=([^\r\n]+)$')
    if (-not $match.Success) { throw 'config.local.env 中缺少 MTL_SERVER_HOST' }
    $SourceHost = $match.Groups[1].Value.Trim()
}
if (-not $NewHost) { $NewHost = Read-Host '新服务器 IP 或域名' }
if ($SourceHost -eq $NewHost) {
    Write-Host '当前部署配置已指向新机，请输入旧服务器地址。' -ForegroundColor Yellow
    $SourceHost = Read-Host '旧服务器 IP 或域名'
}
foreach ($name in @($SourceHost, $NewHost)) {
    if ($name -notmatch '^[a-zA-Z0-9.-]+$') { throw "非法服务器地址: $name" }
}
if ($SourceHost -eq $NewHost) { throw '源服务器与新服务器相同；请用 -SourceHost 指定旧服务器' }
if ($RemoteDir -notmatch '^/[a-zA-Z0-9/_-]+$') { throw '远端目录包含不允许的字符' }
$source = "${SshUser}@${SourceHost}"
$target = "${SshUser}@${NewHost}"
$identityPath = Join-Path $env:USERPROFILE '.ssh\mtl-migration-ed25519'
$stage = Join-Path $env:USERPROFILE 'Desktop\mtl-migration'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$imageFile = Join-Path $stage 'mtl-migration-image.tar'
$dbFile = Join-Path $stage 'mtl_server_final.db'
$filesFile = Join-Path $stage 'mtl-migration-files.tar'
$sourceStopped = $false

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
    Get-Content -LiteralPath "$identityPath.pub" -Raw | & ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -p $SshPort $server 'umask 077; mkdir -p ~/.ssh; chmod 700 ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys'
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
function Check-Db([string]$path) {
    $result = & python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0]); c.close()" $path
    if ($LASTEXITCODE -ne 0 -or $result.Count -lt 2 -or $result[0] -ne 'ok') { throw '本机 SQLite 完整性检查失败' }
    $count = [int]$result[1]
    if ($count -lt 1) { throw '本机数据库为空，停止迁移' }
    return $count
}

try {
    Write-Host "迁移脚本：$PSCommandPath（SSH 密钥认证 / 二进制直传）"
    Write-Host "源机 $SourceHost -> 新机 $NewHost；本机暂存 $stage"
    Initialize-MigrationKey
    Ensure-KeyAccess $source '旧服务器'
    Ensure-KeyAccess $target '新服务器'
    $sourceImage = Invoke-Remote $source "docker inspect --format '{{.Image}}' $container"
    if ($sourceImage -notmatch '^sha256:[0-9a-f]{64}$') { throw '无法确认源容器镜像 ID' }
    $targetContainer = Invoke-Remote $target "docker ps -aq --filter name=^/${container}`$"
    if ($targetContainer) { throw '新机已有同名容器，停止以免覆盖' }

    Invoke-Remote $source "docker tag $sourceImage $imageTag" | Out-Null
    $sourceRuntime = Invoke-Remote $source "docker image inspect --format '{{json .RootFS.Layers}}|{{json .Config.Cmd}}|{{json .Config.Env}}' $sourceImage"
    $matchingImage = $null
    $targetImages = Invoke-Remote $target "docker image ls --no-trunc --format '{{.ID}}'"
    foreach ($candidate in ($targetImages -split "`n" | Select-Object -Unique)) {
        if (-not $candidate) { continue }
        if ((Invoke-Remote $target "docker image inspect --format '{{json .RootFS.Layers}}|{{json .Config.Cmd}}|{{json .Config.Env}}' $candidate") -eq $sourceRuntime) {
            $matchingImage = $candidate
            break
        }
    }
    if ($matchingImage) {
        Write-Host '新机已有相同运行镜像，直接复用。'
        Invoke-Remote $target "docker tag $matchingImage $imageTag" | Out-Null
    } else {
        Write-Host '导出源容器镜像并加载到新机...'
        Invoke-Remote $source "docker save -o $RemoteDir/mtl-migration-image.tar $imageTag" | Out-Null
        Copy-FromRemote $source "$RemoteDir/mtl-migration-image.tar" $imageFile
        Copy-ToRemote $imageFile $target '/root/mtl-migration-image.tar'
        Invoke-Remote $target 'docker load -i /root/mtl-migration-image.tar' | Out-Host
    }
    $targetRuntime = Invoke-Remote $target "docker image inspect --format '{{json .RootFS.Layers}}|{{json .Config.Cmd}}|{{json .Config.Env}}' $imageTag"
    if ($sourceRuntime -ne $targetRuntime) { throw '镜像层或运行配置不一致，停止迁移' }
    Invoke-Remote $target "mkdir -p ${RemoteDir}/data ${RemoteDir}/attachments ${RemoteDir}/reports ${RemoteDir}/log" | Out-Null
    $existing = Invoke-Remote $target "docker run --rm -v ${RemoteDir}/data:/app/server/data $imageTag sqlite3 /app/server/data/mtl_server.db 'SELECT COUNT(*) FROM sqlite_master;'"
    if ([int]$existing -gt 0) { throw '新机已有非空数据库，停止以免覆盖' }

    $isRunning = Invoke-Remote $source "docker inspect --format '{{.State.Running}}' $container"
    if ($isRunning -eq 'true') {
        Write-Host '停止旧服务，开始最终切换...'
        Invoke-Remote $source "docker stop $container" | Out-Host
        $sourceStopped = $true
    } elseif ($isRunning -eq 'false') { $sourceStopped = $true }
    else { throw '无法确定旧容器状态' }

    $backupOutput = Invoke-Remote $source "docker run --rm -v ${RemoteDir}/data:/app/server/data $imageTag /app/server/scripts/backup_sqlite.sh"
    $backupMatch = [regex]::Match($backupOutput, 'app-\d{4}-\d{2}-\d{2}-\d{6}\.db')
    if (-not $backupMatch.Success) { throw "无法解析最终快照: $backupOutput" }
    Copy-FromRemote $source "$RemoteDir/data/backups/$($backupMatch.Value)" $dbFile
    $objectCount = Check-Db $dbFile
    $localHash = (Get-FileHash -LiteralPath $dbFile -Algorithm SHA256).Hash.ToLowerInvariant()
    $sourceHash = (Invoke-Remote $source "sha256sum $RemoteDir/data/backups/$($backupMatch.Value)").Split(' ')[0].ToLowerInvariant()
    if ($localHash -ne $sourceHash) { throw '最终快照下载 SHA256 不匹配' }
    Write-Host "最终快照检查通过：$objectCount 个数据库对象"

    Invoke-Remote $source "mkdir -p ${RemoteDir}/attachments ${RemoteDir}/reports" | Out-Null
    Invoke-Remote $source "tar -C $RemoteDir -cf $RemoteDir/mtl-migration-files.tar attachments reports" | Out-Null
    Copy-FromRemote $source "$RemoteDir/mtl-migration-files.tar" $filesFile
    $filesHash = (Get-FileHash -LiteralPath $filesFile -Algorithm SHA256).Hash.ToLowerInvariant()
    $sourceFilesHash = (Invoke-Remote $source "sha256sum $RemoteDir/mtl-migration-files.tar").Split(' ')[0].ToLowerInvariant()
    if ($filesHash -ne $sourceFilesHash) { throw '附件/报告归档下载 SHA256 不匹配' }

    Copy-ToRemote $filesFile $target '/root/mtl-migration-files.tar'
    $targetFilesHash = (Invoke-Remote $target 'sha256sum /root/mtl-migration-files.tar').Split(' ')[0].ToLowerInvariant()
    if ($filesHash -ne $targetFilesHash) { throw '附件/报告归档上传 SHA256 不匹配' }
    Copy-ToRemote $dbFile $target "$RemoteDir/data/mtl_server.migrating.db"
    $check = Invoke-Remote $target "docker run --rm -v ${RemoteDir}/data:/app/server/data $imageTag sqlite3 /app/server/data/mtl_server.migrating.db 'PRAGMA integrity_check; SELECT COUNT(*) FROM sqlite_master;'"
    if ($check -ne "ok`n$objectCount") { throw "新机数据库检查失败: $check" }
    $remoteHash = (Invoke-Remote $target "sha256sum ${RemoteDir}/data/mtl_server.migrating.db").Split(' ')[0].ToLowerInvariant()
    if ($localHash -ne $remoteHash) { throw '新机数据库 SHA256 不匹配' }
    Invoke-Remote $target "tar -C $RemoteDir -xf /root/mtl-migration-files.tar" | Out-Null
    Invoke-Remote $target "mv -f ${RemoteDir}/data/mtl_server.migrating.db ${RemoteDir}/data/mtl_server.db" | Out-Null

    $run = "docker run -d --name $container --restart unless-stopped -e MYTIMELOGGER_SERVER_MODE=1 -e MYTIMELOGGER_ENVIRONMENT=testing -e SERVER_RUNTIME_OVERWRITE=1 -e SERVER_SLEEP_DB_PATH=/app/server/data/mtl_server.db -p ${AppPort}:8000 -v ${RemoteDir}/data:/app/server/data -v ${RemoteDir}/attachments:/app/server/attachments -v ${RemoteDir}/reports:/app/reports -v ${RemoteDir}/log:/app/server/log $imageTag"
    Invoke-Remote $target $run | Out-Host
    $healthy = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri "http://${NewHost}:${AppPort}/ping" -UseBasicParsing -TimeoutSec 4
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch { }
    }
    if (-not $healthy) { throw '新机 HTTP /ping 未通过；检查容器日志，旧机仍可回滚' }
    $updated = [regex]::Replace($configText, '(?m)^MTL_SERVER_HOST=[^\r\n]+$', "MTL_SERVER_HOST=$NewHost")
    [IO.File]::WriteAllText($configPath, $updated, [Text.UTF8Encoding]::new($false))
    Write-Host "迁移成功：HTTP /ping=200，数据库对象=$objectCount；客户端服务地址改为 http://${NewHost}:${AppPort}" -ForegroundColor Green
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($sourceStopped) { Write-Warning "旧机已停。若新机未接收写入，可运行：ssh -p $SshPort $source 'docker start $container' 回滚。" }
    else { Write-Warning "迁移未完成，请检查旧机容器是否仍已停止：ssh -p $SshPort $source 'docker inspect --format {{.State.Running}} $container'" }
    throw
}
