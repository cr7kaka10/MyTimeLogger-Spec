# MyTimeLogger 测试环境部署指南

## 前置要求

| 工具 | 用途 | 安装 |
|------|------|------|
| **Node.js** 20 LTS | UI 构建 + Electron 打包 | https://nodejs.org/ |
| **Docker Desktop** | 服务端镜像构建 | https://www.docker.com/products/docker-desktop/ |
| **OpenSSH** | 连接测试服务器 | Windows 10+ 自带 |

## 快速开始

```powershell
# 首次复制本机部署目标（保持 ignored）
Copy-Item .\deploy\config.example.env .\deploy\config.local.env

# 双击运行测试部署
.\deploy\deploy-test.bat

# 一键部署（交互式菜单）
Set-Location .\deploy
.\deploy-all.ps1 -Environment testing
```

双击 `deploy-test.bat` 后，窗口会在成功、失败或警告状态停住，等你按键后才返回菜单。容器 ID 只代表创建命令返回；脚本还会检查容器状态、最近日志和 HTTP 可达性。

## 各脚本说明

### deploy-all.ps1 — 一键总入口

交互式菜单，可选：
- `[1]` 全部部署（服务端 + 桌面 EXE）
- `[2]` 仅部署服务端
- `[3]` 仅打包桌面 EXE
- `[4]` 打包 Android APK（开发中）

### deploy-server.ps1 — 服务端部署

本地构建 Docker 镜像 → 导出 tar.gz → SCP 上传到服务器 → 远程 docker load + docker run。
部署后会检查容器是否仍在运行，打印最近日志，并从本机访问 `http://服务器:8000/docs` 验证服务是否可达。

```powershell
# 完整部署
.\deploy-server.ps1 -Environment testing

# 跳过镜像构建（使用已有 tar）
.\deploy-server.ps1 -Environment testing -SkipBuild

# 显式指定本机部署目标配置
.\deploy-server.ps1 -Environment testing -ConfigPath .\config.local.env
```

**首次使用**会提示输入 SSH 密码。建议配置 SSH 密钥免密登录：
```powershell
# 生成密钥（如果没有）
ssh-keygen -t ed25519

# 复制公钥到服务器
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh -l deploy-user example.com "mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys"
```

### build-desktop.ps1 — 桌面 EXE 打包

构建 UI → electron-builder → portable EXE → 复制到桌面。

```powershell
# 完整打包
.\build-desktop.ps1

# 跳过 UI 构建（已有 ui/dist 时加速）
.\build-desktop.ps1 -SkipUiBuild

# 不复制到桌面
.\build-desktop.ps1 -NoCopyDesktop
```

输出：`desktop/dist/MyTimeLogger-1.0.0-portable.exe`

#### winCodeSign 缓存与权限

Windows portable EXE 打包会用到 electron-builder 的 `winCodeSign-2.6.0.7z`。该组件会缓存在 `%LOCALAPPDATA%\electron-builder\Cache\winCodeSign`，缓存完整可用时不会每次重新下载。

如果缓存缺失、不完整，或当前 Windows 会话没有符号链接权限，打包会在 electron-builder 前停止并显示中文诊断。常见处理方式：

- 用管理员权限重新运行 `deploy-test.bat` 或 `build-desktop.ps1`。
- 开启 Windows 开发者模式后，重新打开终端再打包。
- 在网络可访问 GitHub 的环境中提前完成一次打包，让 `%LOCALAPPDATA%\electron-builder\Cache\winCodeSign` 生成完整缓存。
- 如果提示 GitHub 下载不可用，先恢复网络或手动预置完整的 `winCodeSign-2.6.0.7z` 解压缓存。

### build-android.ps1 — Android Debug APK

使用现有 Capacitor Android 工程构建未签名 Debug APK，不需要真机、模拟器或 ADB：

```powershell
.\build-android.ps1
```

前置条件：Node.js、JDK 21、Android SDK 和 `ui/android/gradlew.bat`。脚本依次执行 Android Web staging、`npx cap sync android` 和 `assembleDebug`，成功后输出：

`deploy/artifacts/MyTimeLogger-debug.apk`

`deploy-test.bat` 菜单中的 `[4] Android APK (Debug)` 调用同一入口。APK 产物目录保持 ignored；该流程不会安装 APK、启动模拟器或执行 ADB。

## 配置文件

### config.local.env

从 `config.example.env` 复制；只保存 SSH 部署目标、远端目录和端口，必须保持 ignored。环境由 `-Environment development|testing|production` 参数选择。客户端服务地址和账号在登录页填写，TickTick/S3/AI 等 provider 配置在登录后按用户导入。

`config.ps1` 只验证已加载的私有部署目标，不包含真实主机、账号或目录 fallback。旧 `config.<environment>.local.env` 仅在兼容期读取并提示迁移。

### server/config.json

服务端 `server/config.json` 只保存 CORS、日志、端口、登录限制等非用户运行配置。滴答清单、S3 容灾、AI 大模型和 aTimeLogger 凭据由每个登录用户在自己的配置中填写。

```powershell
http://<服务器>:8000/config
```

`deploy/config.example.env` 只包含安全占位的 SSH 目标、目录和端口。服务端容器使用无秘密运行默认值；不得上传共享 provider `.env`，也不得在 deploy env 中填写应用账号或外部服务密钥。

## 目录结构

```
deploy/
├── deploy-all.ps1          ← 一键总入口
├── deploy-server.ps1       ← 服务端部署
├── build-desktop.ps1       ← 桌面 EXE 打包
├── check-wincodesign.ps1   ← Windows portable 打包预检
├── build-android.ps1       ← Android Debug APK 打包
├── load-private-env.ps1    ← 单一私有配置解析器
├── config.example.env      ← 可提交安全模板
├── config.local.env        ← 本机部署目标（ignored）
├── config.ps1              ← 已加载配置校验/映射
└── README.md               ← 本文档

desktop/dist/               ← EXE 输出目录（gitignore）
deploy/artifacts/           ← Android Debug APK 输出目录（gitignore）
```

## 常见问题

### 看到 Docker 容器 ID 后不知道是否成功
容器 ID 不是最终成功标志。继续看脚本最后的状态：
- `[OK] HTTP verification passed`：服务已从本机访问成功。
- `[WARN] Container is running, but HTTP verification did not pass yet`：容器还在运行，但端口可能仍在启动或被防火墙拦截。
- `[FAIL] SSH deploy or container startup check failed`：远程命令失败或容器启动后退出，优先看脚本打印的 `Recent container logs`。

手动检查：
```powershell
Invoke-WebRequest -Uri http://example.com:8000/docs -UseBasicParsing
ssh -p 22 -l deploy-user example.com "docker ps -a --filter name=mytimelogger-sleep-server"
ssh -p 22 -l deploy-user example.com "docker logs --tail 80 mytimelogger-sleep-server"
```

### Docker build 报错 `COPY failed`
确保从项目根目录运行，或检查 `.dockerignore` 是否排除了必要文件。

### SSH 连接超时
检查服务器防火墙是否开放 SSH 端口（默认 22）和应用端口（默认 8000）。

### electron-builder 报错 `cannot find module better-sqlite3`
需要 rebuild 原生模块：
```powershell
cd desktop
npx electron-rebuild
```

### electron-builder 报错 `Cannot create symbolic link`
这是 `winCodeSign-2.6.0.7z` 解压阶段的 Windows 符号链接权限问题，不是重复下载能解决的问题。请用管理员权限运行，或开启 Windows 开发者模式后重新打开终端。

### EXE 启动后白屏
确认打包前已执行 `npm --prefix ui run build`，且 `ui/dist/index.html` 存在。
