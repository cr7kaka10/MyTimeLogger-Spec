## 1. 修复测试源码位置

- [ ] 1.1 用 Git 将 `tests/runtime/test-android-transport-readiness.ps1` 移到 `tests/unit/`，不改脚本内容；DoD：Git 显示重命名，原回归脚本在新位置能解析 `scripts/start-android-dev.ps1`。（≤2 文件/≤50 行）

## 2. 验证部署入口

- [ ] 2.1 运行迁移后的 PowerShell 回归脚本、`git ls-files -ci --exclude-standard` 与 testing 安全预检；DoD：两组脚本断言通过、非 `openspec/` 的忽略跟踪路径为空、预检输出 `[OK] Security preflight passed.`。（≤2 文件/≤50 行）
- [ ] 2.2 提交迁移及验证记录；DoD：提交包含 Git 重命名，工作树干净，记录安全预检和回归结果。（≤3 文件/≤50 行）
