## ADDED Requirements

### Requirement: 修改 KR 标题
系统 SHALL 在每个 KR 上提供修改入口，允许所属账号将标题修改为非空文本，并同步修改结果。

#### Scenario: 修改重复 KR 的标题
- **GIVEN** 用户可见自己账号下的 KR
- **WHEN** 用户打开修改、输入非空标题并保存
- **THEN** 当前页面显示新标题，其他端同步后也显示新标题

#### Scenario: 拒绝无效或越权修改
- **GIVEN** 标题为空或 KR 不属于当前账号
- **WHEN** 用户提交修改
- **THEN** 服务端拒绝操作且原 KR 保持不变

### Requirement: 确认删除 KR
系统 SHALL 在每个 KR 上提供删除入口；用户确认后删除该 KR 及其学习单元，发布同步删除变更，同时保留独立清单任务和历史流水。

#### Scenario: 删除重复 KR
- **GIVEN** 用户可见重复的 KR
- **WHEN** 用户点击删除并确认
- **THEN** 该 KR 及其学习单元从当前页消失，其他端同步后也不再显示

#### Scenario: 取消删除
- **GIVEN** 删除确认框展示 KR 标题及学习单元数量
- **WHEN** 用户取消
- **THEN** KR、学习单元和关联记录均保持不变

#### Scenario: 拒绝越权删除
- **GIVEN** KR 不属于当前账号
- **WHEN** 用户提交删除命令
- **THEN** 服务端拒绝操作且该 KR 及其学习单元保持不变
