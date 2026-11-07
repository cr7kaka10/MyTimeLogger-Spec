## Context

`deploy/deploy-test.bat` 在菜单前调用 `deploy/security-preflight.ps1`。预检以 `git ls-files -ci --exclude-standard` 检出被忽略的跟踪文件；除了 `openspec/` 的既有例外，其余路径均失败。`tests/runtime/` 专供本地测试产物，根 `.gitignore` 忽略它；新提交的 Android 回归脚本恰好位于此处。当前 Git 检查只发现这一份非 OpenSpec 的违规文件。

## Goals / Non-Goals

**Goals:**
- 使 Android 回归脚本继续受版本控制，并让部署安全预检通过。
- 保留对 `tests/runtime/` 中误提交文件的拦截。

**Non-Goals:**
- 修改安全规则、部署配置或 Android 启动代码。
- 执行服务端发布、数据库迁移或客户端安装。

## Decisions

- 使用 Git 重命名将脚本移至 `tests/unit/test-android-transport-readiness.ps1`。两处目录同处 `tests/` 下，脚本中上溯两级定位 `scripts/start-android-dev.ps1` 的相对路径无需改变。备选为在 `.gitignore` 或预检中豁免单文件；这会让运行产物目录容纳源代码，削弱现有边界，故不采用。
- 保持脚本内容原样；先运行脚本验证断言，再运行安全预检并核对 `git ls-files -ci --exclude-standard` 的非 OpenSpec 输出为空。这样直接覆盖截图中的失败条件。若有其它违规路径，单独定位，不扩大本提案范围。

## Risks / Trade-offs

- [其它文档或手工命令引用旧路径] → 核查本次变更及近期 Android 提案中的显式引用，并在需要时更新。
- [预检后续发现另一条规则失败] → 记录具体规则和路径，独立判断，不绕开安全门。

## Migration Plan

批准后迁移脚本，验证通过并提交；重新打开部署菜单即可复验。回滚该提交会恢复原位置和原阻断，无数据迁移。

## Open Questions

无。
