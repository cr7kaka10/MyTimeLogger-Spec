## Why

2026-11-07 的 Android 传输就绪回归脚本被提交到 `tests/runtime/`，而根目录 `.gitignore` 忽略该目录。测试部署在展示菜单前执行安全预检，按既有规则拒绝这份“已跟踪且被忽略”的文件，导致所有部署选项无法进入。

## What Changes

- 将该回归脚本移到受版本控制的 `tests/unit/`，保持脚本断言和相对路径行为。
- 核对 Git 索引中不再有 `tests/runtime/` 文件，并执行回归脚本与部署安全预检。
- 排除项：不放宽安全预检，不更改部署配置、菜单或 Android 传输逻辑，不触碰服务器数据和运行中的服务。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deployment`：明确受版本控制的回归脚本不能放在仅用于本地运行产物的 `tests/runtime/`，且安全预检在此类路径出现时继续阻断。

## Impact

- 影响现有模块：Android 启动回归脚本的仓库位置、部署前的 Git 安全预检；测试部署菜单会恢复可进入状态。
- PC 客户端、服务端和 Android 运行时代码、API 与依赖均不变。
- 回滚方案：回退文件迁移提交，原有安全预检阻断会恢复；无数据迁移。
