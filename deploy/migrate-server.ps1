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
if ($SshUser -notmatch '^[a-zA-Z0-9_-]+$') { throw "非法 SSH 用户: $SshUser" }
if ($SshUser -ne 'root') { throw '简化迁移目前需要 root SSH 用户' }
if ($RemoteDir -notmatch '^/[a-zA-Z0-9/_-]+$') { throw '远端目录包含不允许的字符' }
if ($configText -notmatch '(?m)^MTL_SERVER_HOST=') { throw 'config.local.env 中缺少 MTL_SERVER_HOST' }
$target = "${SshUser}@${NewHost}"
$identityPath = Join-Path $env:USERPROFILE '.ssh\mtl-migration-ed25519'
$stage = Join-Path $env:USERPROFILE 'Desktop\mtl-migration'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$imageFile = Join-Path $stage 'mtl-migration-image.tar'
if (-not $SnapshotPath) { $SnapshotPath = Join-Path $stage 'mtl_server_final.db' }
if (-not (Test-Path -LiteralPath $SnapshotPath)) { throw "本机 SQLite 快照不存在: $SnapshotPath" }

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
function Check-Db([string]$path) {
    $result = & python -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0]); c.close()" $path
    if ($LASTEXITCODE -ne 0 -or $result.Count -lt 2 -or $result[0] -ne 'ok') { throw '本机 SQLite 完整性检查失败' }
    $count = [int]$result[1]
    if ($count -lt 1) { throw '本机数据库为空，停止迁移' }
    return $count
}

try {
    Write-Host "迁移脚本：$PSCommandPath（本地构建 + SQLite 快照恢复）"
    Write-Host "本机快照 $SnapshotPath -> 新机 $NewHost"
    if ($SourceHost) { Write-Host '当前使用本机快照，不连接旧服务器。' -ForegroundColor Yellow }
    $objectCount = Check-Db $SnapshotPath
    $localHash = (Get-FileHash -LiteralPath $SnapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "本机快照检查通过：$objectCount 个数据库对象"
    & docker build -t $localImageTag -f (Join-Path $projectRoot 'server\Dockerfile') $projectRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw '本地服务端镜像构建失败' }
    $localRuntime = & docker image inspect --format '{{json .RootFS.Layers}}|{{json .Config.Cmd}}|{{json .Config.Env}}' $localImageTag
    if ($LASTEXITCODE -ne 0) { throw '无法读取本地构建镜像' }
    $localRuntime = ($localRuntime -join "`n").Trim()
    Initialize-MigrationKey
    Ensure-KeyAccess $target '新服务器'
    $targetContainer = Invoke-Remote $target "docker ps -aq --filter name=^/${container}`$"
    if ($targetContainer) { throw '新机已有同名容器，停止以免覆盖' }

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
    $existing = Invoke-Remote $target "if test -s ${RemoteDir}/data/mtl_server.db; then docker run --rm -v ${RemoteDir}/data:/app/server/data $imageTag sqlite3 /app/server/data/mtl_server.db 'SELECT COUNT(*) FROM sqlite_master;'; else echo 0; fi"
    if ([int]$existing -gt 0) { throw '新机已有非空数据库，停止以免覆盖' }

    Copy-ToRemote $SnapshotPath $target "$RemoteDir/data/mtl_server.migrating.db"
    $check = Invoke-Remote $target "docker run --rm -v ${RemoteDir}/data:/app/server/data $imageTag sqlite3 /app/server/data/mtl_server.migrating.db 'PRAGMA integrity_check; SELECT COUNT(*) FROM sqlite_master;'"
    if ($check -ne "ok`n$objectCount") { throw "新机数据库检查失败: $check" }
    $remoteHash = (Invoke-Remote $target "sha256sum ${RemoteDir}/data/mtl_server.migrating.db").Split(' ')[0].ToLowerInvariant()
    if ($localHash -ne $remoteHash) { throw '新机数据库 SHA256 不匹配' }
    Invoke-Remote $target "if test -e ${RemoteDir}/data/mtl_server.db; then if test -e ${RemoteDir}/data/mtl_server.empty-pre-migration.db; then exit 1; fi; mv ${RemoteDir}/data/mtl_server.db ${RemoteDir}/data/mtl_server.empty-pre-migration.db; fi; mv ${RemoteDir}/data/mtl_server.migrating.db ${RemoteDir}/data/mtl_server.db" | Out-Null

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
    if (-not $healthy) { throw '新机 HTTP /ping 未通过；请检查新机容器日志' }
    $updated = [regex]::Replace($configText, '(?m)^MTL_SERVER_HOST=[^\r\n]+$', "MTL_SERVER_HOST=$NewHost")
    [IO.File]::WriteAllText($configPath, $updated, [Text.UTF8Encoding]::new($false))
    Write-Host "迁移成功：HTTP /ping=200，数据库对象=$objectCount；客户端服务地址改为 http://${NewHost}:${AppPort}" -ForegroundColor Green
    Write-Warning '此脚本只恢复服务端镜像和 SQLite；历史附件、报告及 S3 备份配置需单独迁移。'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Warning '迁移未完成；本机 SQLite 快照未改动。请检查新机容器状态后再重试。'
    throw
}
