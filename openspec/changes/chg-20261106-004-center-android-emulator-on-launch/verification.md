# 安卓模拟器窗口居中验收（北京时间 2026-11-06）

- 修复前目标 QEMU PID 17664 的窗口矩形为 `516,-826,1008,275`，屏幕工作区 `0,0,1920,1020`；手动调用已有 `ensure-window-visible.ps1` 后为 `755,51,1165,969`，两秒后稳定。原启动顺序为 `avd_acquisition → boot_wait → foreground_boot`；就绪失败时 `foreground_boot` 不会执行。
- 实现将 `foreground_launch` 放在目标 QEMU PID 识别后、`boot_wait` 前；窗口 PID 必须仍等于该目标 PID，GUI 句柄最多尝试 30 次、间隔 500 ms。原有启动成功后的居中调用保留。
- 复用目标 AVD 现场测试：故意将 PID 17664 窗口置于 `516,-500,925,417`，脚本于 18:53:41 先在 `foreground_launch` 一次定位到 `756,52,1165,969`，随后才记录 `boot_wait`；两秒后矩形未变化。
- 冷启动现场测试：目标 QEMU PID 25592 于 18:57:19 启动，窗口起点 `516,-826,1020,276`；18:57:27 的第 14 次检查将它定位到 `755,51,1165,969`，然后进入 `boot_wait`；两秒后为 `755,51,1164,968`。中途 Qt 曾改变窗口尺寸，下一次重试成功校正。
- 冷启动后原有 Android 传输检查仍在 18:59:07 报 `adb_transport_unavailable`，属于老板明确取消的端口检测提案范围；窗口仍位于中央。随后手动配置 `adb reverse`、启动 `MainActivity`，焦点为 `com.mytimelogger.app/.MainActivity`。
- `python -m pytest tests/unit/test_android_emulator_window_bounds.py -q`：1 passed；PowerShell 解析无错误；OpenSpec strict 与 `git diff --check` 通过。实现提交：`c02cf2ac`。
