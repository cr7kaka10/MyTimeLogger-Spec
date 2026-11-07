## 1. 修复测试源码位置

- [x] 1.1 用 Git 将 `tests/runtime/test-android-transport-readiness.ps1` 移到 `tests/unit/`，不改脚本内容；DoD：Git 显示重命名，原回归脚本在新位置能解析 `scripts/start-android-dev.ps1`。（≤2 文件/≤50 行）

## 2. 验证部署入口

- [x] 2.1 运行迁移后的 PowerShell 回归脚本、`git ls-files -ci --exclude-standard` 与 testing 安全预检；DoD：两组脚本断言通过、非 `openspec/` 的忽略跟踪路径为空、预检输出 `[OK] Security preflight passed.`。（≤2 文件/≤50 行）
- [x] 2.2 从 `deploy-test.bat` 启动并在菜单选 `0` 退出；DoD：不再出现截图中的预检失败，菜单显示 `[0-6]` 选项，退出前没有执行实际部署。（≤1 文件/≤50 行）
- [x] 2.3 提交迁移及验证记录；DoD：提交包含 Git 重命名，工作树干净，记录安全预检、回归和菜单启动结果。（≤3 文件/≤50 行）

## 验收记录（北京时间 2026-11-07）

- `git mv` 显示 `tests/{runtime => unit}/test-android-transport-readiness.ps1 (100%)`；新位置的相对路径解析到现有 `scripts/start-android-dev.ps1`。
- PowerShell 回归输出：`Android transport readiness regression passed.`、`Android reverse verification regression passed.`；退出码 0。
- 非 `openspec/` 的 `git ls-files -ci --exclude-standard` 结果数为 0；testing 安全预检输出 `[OK] Security preflight passed.`，退出码 0。
- `deploy-test.bat --inner` 输入 `0` 后：安全预检通过、出现 `Select [0-6]` 和 Android 菜单项、退出码 0；无预检失败，也未启动部署。
