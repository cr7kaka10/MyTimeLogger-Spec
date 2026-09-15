# ═══════════════════════════════════════════════════════════════
# MyTimeLogger 服务端部署脚本
# 流程：本地构建 Docker 镜像 → 导出 → SCP 上传 → 远程加载启动
# ═══════════════════════════════════════════════════════════════
param(
    [switch]$SkipBuild,      # 跳过镜像构建，直接用已有 tar
    [switch]$SkipUpload,     # 跳过上传，直接在服务器上操作
    [ValidateSet("development", "testing", "production")]
    [string]$Environment = "testing",
    [string]$ConfigPath,
    [switch]$PrivateConfigLoaded
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $PrivateConfigLoaded) {
    . "$PSScriptRoot\load-private-env.ps1" -Environment $Environment -ConfigPath $ConfigPath -RequireComplete -Quiet
}
. "$PSScriptRoot\config.ps1"

function Exit-OnError {
    param([string]$msg)
    if ($LASTEXITCODE -ne 0) {
        Write-Err $msg
        throw $msg
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  MyTimeLogger 服务端部署" -ForegroundColor Magenta
Write-Host "  目标：$SERVER_USER@$SERVER_HOST`:$SERVER_PORT" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Magenta

# ── 第1步：检查 Docker Desktop ──
Write-Step "检查 Docker 环境..."
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker 未运行" }
    Write-Ok "Docker 版本: $dockerVersion"
} catch {
    Write-Err "Docker Desktop 未运行或未安装，请先启动 Docker Desktop"
    throw "Docker Desktop 未运行或未安装"
}

# ── 第2步：构建 Docker 镜像 ──
if (-not $SkipBuild) {
    Write-Step "构建 Docker 镜像 ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}..."
    Push-Location $PROJECT_ROOT
    try {
        docker build -t "${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}" -f server/Dockerfile .
        Exit-OnError "Docker 镜像构建失败"
        Write-Ok "镜像构建成功"
    } finally {
        Pop-Location
    }

    # ── 第3步：导出镜像 ──
    Write-Step "导出镜像为 tar.gz..."
    if (Test-Path $DOCKER_IMAGE_TAR) { Remove-Item $DOCKER_IMAGE_TAR -Force }
    docker save "${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}" | gzip > $DOCKER_IMAGE_TAR
    Exit-OnError "镜像导出失败"
    $tarSize = [math]::Round((Get-Item $DOCKER_IMAGE_TAR).Length / 1MB, 1)
    Write-Ok "镜像已导出: $DOCKER_IMAGE_TAR ($tarSize MB)"
} else {
    Write-Warn "跳过镜像构建（使用 -SkipBuild）"
    if (-not (Test-Path $DOCKER_IMAGE_TAR)) {
        Write-Err "未找到已导出的镜像: $DOCKER_IMAGE_TAR"
        throw "未找到已导出的镜像"
    }
}

# ── 第4步：上传到服务器 ──
if (-not $SkipUpload) {
    Write-Step "上传镜像到服务器..."
    Write-Info "目标目录: $REMOTE_DEPLOY_DIR"

    # 在服务器上创建目录结构
    ssh -p $SERVER_PORT "$SERVER_USER@$SERVER_HOST" "mkdir -p $REMOTE_DEPLOY_DIR/{data,attachments,reports,log}"
    Exit-OnError "SSH 创建目录失败"

    # 上传镜像
    Write-Info "上传 Docker 镜像（可能需要几分钟）..."
    scp -P $SERVER_PORT $DOCKER_IMAGE_TAR "${SERVER_USER}@${SERVER_HOST}:${REMOTE_DEPLOY_DIR}/mytimelogger-server.tar.gz"
    Exit-OnError "镜像上传失败"
    Write-Ok "镜像上传完成"

} else {
    Write-Warn "跳过上传（使用 -SkipUpload）"
}

# ── 第5步：远程部署 ──
Write-Step "远程部署容器..."

$remoteScript = @"
set -e
echo '>>> 加载 Docker 镜像...'
docker load -i $REMOTE_DEPLOY_DIR/mytimelogger-server.tar.gz

echo '>>> 停止旧容器（如存在）...'
docker stop $DOCKER_CONTAINER_NAME 2>/dev/null || true
docker rm $DOCKER_CONTAINER_NAME 2>/dev/null || true

echo '>>> 启动新容器...'
container_id=`$(docker run -d \
    --name $DOCKER_CONTAINER_NAME \
    --restart unless-stopped \
    -e MYTIMELOGGER_SERVER_MODE=1 \
    -e MYTIMELOGGER_ENVIRONMENT=$Environment \
    -e SERVER_RUNTIME_OVERWRITE=1 \
    -e SERVER_SLEEP_DB_PATH=/app/server/data/mtl_server.db \
    -e MYTIMELOGGER_SERVER_LOG_DIR=/app/server/log \
    -e MYTIMELOGGER_REPORTS_DIR=/app/reports \
    -p ${SERVER_APP_PORT}:8000 \
    -v $REMOTE_DEPLOY_DIR/data:/app/server/data \
    -v $REMOTE_DEPLOY_DIR/attachments:/app/server/attachments \
    -v $REMOTE_DEPLOY_DIR/reports:/app/reports \
    -v $REMOTE_DEPLOY_DIR/log:/app/server/log \
    ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG})
echo ">>> Container ID: `$container_id"

echo '>>> 等待服务启动...'
sleep 5

echo '>>> 容器状态：'
container_state=`$(docker inspect -f '{{.State.Status}}' $DOCKER_CONTAINER_NAME)
echo ">>> Container status: `$container_state"
docker ps --filter name=$DOCKER_CONTAINER_NAME --format 'table {{.Status}}\t{{.Ports}}'

echo '>>> 最近日志：'
docker logs --tail 40 $DOCKER_CONTAINER_NAME

if [ "`$container_state" != "running" ]; then
    echo '>>> 容器未保持运行，部署失败。'
    exit 1
fi

cron_file=`$(mktemp)
crontab -l 2>/dev/null | grep -v -e 'mytimelogger-sqlite-backup' -e '^CRON_TZ=Asia/Shanghai`$' > "`$cron_file" || true
printf '%s\n' 'CRON_TZ=Asia/Shanghai' >> "`$cron_file"
printf '%s\n' "0 3 * * * docker exec $DOCKER_CONTAINER_NAME /app/server/scripts/backup_sqlite.sh >> $REMOTE_DEPLOY_DIR/log/sqlite-backup.log 2>&1 # mytimelogger-sqlite-backup" >> "`$cron_file"
crontab "`$cron_file"
rm -f "`$cron_file"
echo '>>> SQLite backup scheduled daily at 03:00 Asia/Shanghai'
"@

ssh -p $SERVER_PORT "$SERVER_USER@$SERVER_HOST" $remoteScript
Exit-OnError "远程部署失败"

# ── 第6步：验证服务 ──
Write-Step "验证服务是否正常启动..."
Start-Sleep -Seconds 2

try {
    $response = Invoke-WebRequest -Uri "http://${SERVER_HOST}:${SERVER_APP_PORT}/docs" -TimeoutSec 10 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Ok "服务验证通过！API 文档地址: http://${SERVER_HOST}:${SERVER_APP_PORT}/docs"
    } else {
        Write-Warn "服务返回状态码: $($response.StatusCode)"
        Write-Info "手动检查: Invoke-WebRequest -Uri http://${SERVER_HOST}:${SERVER_APP_PORT}/docs -UseBasicParsing"
        Write-Info "远程日志: ssh -p $SERVER_PORT $SERVER_USER@$SERVER_HOST `"docker logs --tail 80 $DOCKER_CONTAINER_NAME`""
    }
} catch {
    Write-Warn "无法访问服务，可能需要等待更长启动时间或检查防火墙"
    Write-Info "手动检查: Invoke-WebRequest -Uri http://${SERVER_HOST}:${SERVER_APP_PORT}/docs -UseBasicParsing"
    Write-Info "远程日志: ssh -p $SERVER_PORT $SERVER_USER@$SERVER_HOST `"docker logs --tail 80 $DOCKER_CONTAINER_NAME`""
}

# ── 清理本地临时文件 ──
Write-Step "清理本地临时文件..."
if (Test-Path $DOCKER_IMAGE_TAR) {
    Remove-Item $DOCKER_IMAGE_TAR -Force
    Write-Ok "已删除临时镜像文件"
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ 服务端部署完成！" -ForegroundColor Green
Write-Host "  📍 服务地址: http://${SERVER_HOST}:${SERVER_APP_PORT}" -ForegroundColor Green
Write-Host "  📄 API 文档: http://${SERVER_HOST}:${SERVER_APP_PORT}/docs" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
