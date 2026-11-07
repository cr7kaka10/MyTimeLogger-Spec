## ADDED Requirements

### Requirement: 跟踪的回归脚本位于源码测试目录
部署仓库 SHALL 将需要版本控制的回归脚本放在未被忽略的测试源码目录。`tests/runtime/` SHALL 只用于本地运行产物；安全预检 MUST 继续阻断该目录中被 Git 跟踪的文件。

#### Scenario: 回归脚本可随版本发布并通过预检
- **GIVEN** Android 传输就绪回归脚本受 Git 跟踪，且仓库没有其它非 `openspec/` 的忽略跟踪文件
- **WHEN** 从仓库根目录运行测试部署安全预检
- **THEN** 脚本位于未被忽略的测试源码目录，预检通过 `tracked-but-ignored` 检查

#### Scenario: 运行产物目录误跟踪仍被阻断
- **GIVEN** 某文件受 Git 跟踪且命中 `tests/runtime/` 忽略规则
- **WHEN** 从仓库根目录运行测试部署安全预检
- **THEN** 预检以 `rule=tracked-but-ignored` 和该文件路径失败
