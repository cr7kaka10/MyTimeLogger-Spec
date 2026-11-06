## Why

`start-all.bat` 重复启动时，已有本项目 FastAPI 占用 8000，脚本却再次启动服务端并报 WinError 10048。现场确认本机 `Get-NetTCPConnection -LocalPort 8000` 能返回原进程 PID 23936，但记录的 `State` 为 `null`，所以脚本的 `-State Listen` 筛选漏检。

## What Changes

- 以真实绑定探测判断 8000 是否可用，端口被占用时只处理命令行和工作目录都确认属于本项目的服务端进程；其他占用者明确报错而不终止。
- 启动前与就绪前检查使用一致的端口判断；重复启动时不会再把“已有服务”误判为端口空闲。
- 排除项：不改 FastAPI 接口、数据库、PC/安卓业务逻辑，不清理 IDE、其他项目或未知进程。
- 回滚方案：恢复这两个 PowerShell 启动脚本的原版，当前运行中的服务不受影响。

## Capabilities

### New Capabilities

- `local-startup-port-ownership`: 一键启动准确识别端口占用和本项目进程，并安全重启本地服务。

### Modified Capabilities

无。

## Impact

- 影响本地开发启动链路 `start-all.bat` 调用的 `scripts/start-local-process.ps1` 与 `scripts/wait-local-readiness.ps1`；PC、服务端和安卓联调均受益。
- 不改生产部署或远端服务。现场已临时复用健康服务：`/ping=200`、Vite=200、MyTimeLogger Electron 窗口已打开，安卓模拟器已启动。
