## Why

测试部署在进入部署菜单前运行安全预检，但预检把仓库明确为发布策略忽略的 `openspec/` 文档也纳入“已跟踪但被忽略”拦截。现有 OpenSpec 变更文件虽由 Git 跟踪，仍匹配根目录 `.gitignore` 的 `/openspec/` 规则，导致所有测试部署在安全检查阶段失败。

## What Changes

- 调整安全预检：允许 `openspec/` 下符合项目发布排除策略的已跟踪文件通过“tracked-but-ignored”检查。
- 保留其他目录的已跟踪忽略文件拦截，并用隔离 Git 仓库回归覆盖允许与拒绝两种情况。
- 不改 `deploy-test.bat` 的部署步骤；它只负责调用发生误报的预检脚本。

**排除项：**不改 `.gitignore` 的发布排除策略、部署配置/凭据、服务器部署行为、API、客户端运行逻辑或 OpenSpec 文档是否跟踪。

**回滚方案：**回退安全预检与对应回归测试改动即可恢复原有检查行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deployment`：安全预检应忽略按仓库策略排除的 OpenSpec 规划文件，同时继续拦截其他已跟踪但被忽略的文件。

## Impact

- 影响端：Windows 部署工具所在的 PC/开发环境；该预检会门控测试服务器、桌面 EXE 和 Android APK 部署/构建入口，不改变这三端运行时代码。
- 影响模块：`deploy/security-preflight.ps1`、`tests/unit/test_security_hardening.py`，以及 `openspec/specs/deployment/spec.md` 对应要求。
- 无 API、依赖或数据库变更。
