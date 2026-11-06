## 1. 端口识别

- [ ] 1.1 保存本机端口误判的只读证据（0 文件/0 行）；DoD：记录 PID、命令行、`State=null`、`-State Listen` 空结果与 `/ping=200`。
- [ ] 1.2 修复服务启动前的绑定探测与项目进程归属检查（`scripts/start-local-process.ps1`；1 文件/≤50 行改动）；DoD：同项目旧服务可精确重启，未知 PID 与系统排除端口均拒绝且不终止进程。
- [ ] 1.3 修复空闲端口预检（`scripts/wait-local-readiness.ps1`；1 文件/≤50 行改动）；DoD：占用且 `State=null` 时返回端口不可用，真正空闲时返回成功。

## 2. 回归与提交

- [ ] 2.1 添加 PowerShell 端口归属回归（新增 `tests/unit/test_local_startup_port.ps1`；1 文件/≤50 行）；DoD：覆盖当前项目、未知占用、状态缺失三条路径，测试不杀无关进程。
- [ ] 2.2 连续两次运行本地服务启动与就绪检查，核对 PC 窗口和 `/ping`（0 文件/0 行）；DoD：两次均通过且没有 WinError 10048，当前构建版本正确。
- [ ] 2.3 执行 OpenSpec strict 与脚本回归，提交代码和验证记录（≤1 文档/50 行）；DoD：`verification.md` 包含命令结果、启动 PID 与提交哈希，工作树干净。
