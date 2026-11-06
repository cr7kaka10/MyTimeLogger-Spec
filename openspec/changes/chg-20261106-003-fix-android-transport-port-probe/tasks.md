## 1. 识别目标传输

- [ ] 1.1 记录现场证据（0 文件/0 行）；DoD：`verification.md` 写明目标 QEMU PID、5554/5555 归属、空 `State`、ADB AVD 名称、`sys.boot_completed` 和失败摘要路径。
- [ ] 1.2 以目标 QEMU PID 的监听记录取代 `-State Listen`（`scripts/start-android-dev.ps1`；1 文件/≤35 行改动）；DoD：空 `State` 的目标监听能通过，缺端口或其他 PID 不通过。
- [ ] 1.3 核对 ADB serial 的 AVD 名称（`scripts/start-android-dev.ps1`；1 文件/≤20 行改动）；DoD：其他 AVD 占同一 serial 时不能误复用且不终止其进程。

## 2. 回归和验收

- [ ] 2.1 添加 PowerShell 端口和 ADB 身份回归（新增 `tests/unit/test_android_transport_port.ps1`；1 文件/≤50 行）；DoD：目标、空状态、其他 PID、缺端口和错误 AVD 名称均覆盖。
- [ ] 2.2 在目标 AVD 上连续两次运行 `start-all.bat`（0 文件/0 行）；DoD：两次均报告 PC、Server、Vite、Android ready，Android 摘要 `input_ready=true` 且无未知进程被终止。
- [ ] 2.3 执行 PowerShell 测试与 OpenSpec strict，提交代码及验证记录（≤1 文档/50 行）；DoD：`verification.md` 记录命令、摘要与提交哈希，工作树干净。
