## ADDED Requirements

### Requirement: 安全预检容忍发布排除的 OpenSpec 跟踪文件
部署安全预检 SHALL 允许 `openspec/` 目录中按仓库发布策略忽略但仍由 Git 跟踪的文件通过 `tracked-but-ignored` 检查。该例外 MUST 仅适用于 `openspec/` 根目录下的路径；其它目录中已跟踪且被忽略的文件仍 SHALL 导致预检失败。

#### Scenario: 发布排除的 OpenSpec 文件不阻断预检
- **WHEN** Git 跟踪的 `openspec/` 文件匹配仓库忽略规则
- **THEN** 安全预检不因 `tracked-but-ignored` 规则失败

#### Scenario: 其他目录的已跟踪忽略文件仍被拦截
- **WHEN** Git 跟踪的非 `openspec/` 文件匹配仓库忽略规则
- **THEN** 安全预检以 `tracked-but-ignored` 规则失败
