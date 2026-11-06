# 本地端口误判验收（北京时间 2026-11-06）

- 修复前，本机 8000 由本项目 FastAPI PID 23936 占用且 `/ping=200`，`Get-NetTCPConnection -LocalPort 8000` 的 `State` 为空；六次 `-State Listen` 探测中四次返回空，导致再次绑定 `0.0.0.0:8000` 报 WinError 10048。
- 修复后用独占 TCP 绑定判断端口是否可用；被占时用未过滤 `State` 的连接表找监听 PID，并同时核实 `uvicorn server.server:app` 与本工作区 `--app-dir`。未知/无法确认的占用拒绝终止。
- `tests/unit/test_local_startup_port.ps1` 通过：项目 PID、另一工作区、无关进程、占用和释放后的绑定、`-RequirePortsFree` 占用返回 3 与空闲返回 0。
- 本地服务脚本连续重启两次，`wait-local-readiness.ps1 -Name Server -TimeoutSeconds 20` 通过；监听 PID 曾为 25448、17984，`/ping=ok`，最新 stderr 无 WinError 10048。
- 两次运行完整 `start-all.bat`，FastAPI、Vite、PC Electron 均显示 ready；最终 PC 窗口 PID 7892、Vite HTTP 200、服务 `/ping=ok`。Android 自动阶段仍失败：另一个脚本也用 `Get-NetTCPConnection -State Listen` 判断 5554/5555，遇到相同空 `State`；已单独提出修复，不属于本提案的脚本范围。
- 已手动在目标 `aTimeLogger_Extraction_API35` 模拟器安装最新 APK、配置 `adb reverse tcp:8000` 并启动；`MainActivity` 获得焦点，首页显示“已同步”。
- PowerShell 5.1 脚本解析、`git diff --check`、OpenSpec strict 通过。实现提交：`54d7f18e`。
