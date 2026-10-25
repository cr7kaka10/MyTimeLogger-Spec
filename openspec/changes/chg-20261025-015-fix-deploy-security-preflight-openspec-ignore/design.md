## Context

`deploy/deploy-test.bat` 在展示部署菜单前调用 `deploy/security-preflight.ps1`。预检通过 `git ls-files -ci --exclude-standard` 收集“已跟踪且匹配忽略规则”的路径，并对任一路径立即失败。仓库根 `.gitignore` 有意忽略 `/openspec/` 以排除发布包中的内部规划记录；历史上已跟踪的 OpenSpec 文件仍会出现在该集合中，因此当前安全门在部署前误报。

约束：保持发布排除策略；继续拦截其它目录中意外处于忽略状态的已跟踪文件；只修复预检行为，不改部署菜单或部署配置。

## Goals / Non-Goals

**Goals:**
- 仅将 `openspec/` 下的跟踪忽略文件从该项拦截中豁免。
- 保持其他 tracked-but-ignored 路径失败。
- 用临时 Git 仓库覆盖两种行为，避免依赖当前工作区状态。

**Non-Goals:**
- 修改 `.gitignore`、移除 OpenSpec 跟踪文件或调整发布打包规则。
- 放宽凭据、数据库、个人路径、账户或远端地址扫描。
- 改动服务端、PC/Android 运行时代码和部署步骤。

## Decisions

- 在 `security-preflight.ps1` 的 ignored-path 循环内按仓库相对路径前缀豁免 `openspec/`，其他路径仍执行原有失败逻辑。这样保留安全门的默认拒绝行为，也保留 OpenSpec 发布排除规则。
- 在 `tests/unit/test_security_hardening.py` 中增加临时 Git 仓库回归场景：设置 `/openspec/` 忽略规则并强制跟踪其中一个文件，预检应通过；另外强制跟踪一个被忽略的非 OpenSpec 文件，预检应以 `tracked-but-ignored` 失败。
- 不改 `deploy-test.bat`：它正确地在部署前调用预检，缺陷位于预检路径分类。

## Risks / Trade-offs

- [OpenSpec 路径前缀匹配过宽] → 仅豁免固定的 `openspec/` 根目录，测试验证其它被忽略路径仍拒绝。
- [测试环境缺少 PowerShell 或 Git] → 回归测试沿用当前 security-preflight fixture 的 PowerShell/Git 前置条件；实现阶段需在项目支持的 Windows 环境运行。

## Migration Plan

无需数据迁移或配置迁移。合并后重新运行 `deploy-test.bat` 即可；如出现回归，回退预检和对应测试文件的改动，恢复原拦截行为。

## Open Questions

无。
