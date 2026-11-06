## 1. 启动时立即显示

- [x] 1.1 记录现场窗口矩形和调用顺序（0 文件/0 行）；DoD：`verification.md` 写明目标 PID、修复前窗口/工作区矩形、手动居中结果，以及 `foreground_boot` 当前晚于 `boot_wait` 的证据。
- [x] 1.2 将首次窗口居中移到目标 AVD 进程识别后（`scripts/start-android-dev.ps1`；1 文件/≤15 行改动）；DoD：冷启动与复用路径的日志均先出现 `foreground_launch`，再出现 `boot_wait`，后续就绪失败也不跳过首次居中。
- [x] 1.3 扩大目标窗口句柄的有界等待（`scripts/start-android-dev.ps1`；1 文件/≤15 行改动）；DoD：句柄出现后立刻定位，约 15 秒仍未出现时仅记录诊断，不移动其他窗口。

## 2. 防回归与现场验收

- [x] 2.1 加强现有窗口测试（`tests/unit/test_android_emulator_window_bounds.py`；1 文件/≤25 行改动）；DoD：回归能识别早期居中阶段被移回 `boot_wait` 之后或目标 PID 核对缺失。
- [x] 2.2 在目标 AVD 上验证屏幕外窗口自动复位（0 文件/0 行）；DoD：实测窗口在进入 `boot_wait` 前处于工作区中央，窗口坐标在两秒后仍有效；测试失败时用现有工具恢复居中。
- [x] 2.3 执行定向测试、PowerShell 解析和 OpenSpec strict，提交实现及验证记录（≤1 文档/50 行）；DoD：`verification.md` 记录命令、阶段顺序、实际矩形和提交哈希，工作树干净。
