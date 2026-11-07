## ADDED Requirements

### Requirement: 选餐转盘可抽取候选

PC 和安卓端 SHALL 使用当前账号的同一候选配置；点击转盘按钮 SHALL 打开转盘，抽取结果 MUST 按配置权重产生，动画 SHALL 停在该结果并允许再次抽取。

#### Scenario: 正常抽取
- **GIVEN** 账号配置了多项且权重不同的餐食
- **WHEN** 用户点击“开始”
- **THEN** 系统 SHALL 按各项权重选出一项并在动画结束后显示名称
- **AND** 动画显示的指针结果 MUST 与文字结果一致

#### Scenario: 离线抽取
- **GIVEN** 当前设备无网络且有本地候选配置
- **WHEN** 用户打开并转动转盘
- **THEN** 系统 SHALL 正常抽取且不依赖服务端响应

### Requirement: 设置候选与实际概率

设置页 SHALL 允许编辑 2–12 项餐食的名称、顺序和整数权重，并显示归一化概率；无效配置 MUST 拒绝保存且说明原因。

#### Scenario: 修改权重
- **GIVEN** 有两项权重分别为 1 和 3
- **WHEN** 用户查看设置
- **THEN** 系统 SHALL 显示 25% 和 75% 的实际概率

#### Scenario: 无效配置
- **GIVEN** 候选少于两项、名称重复或权重不在 1–100
- **WHEN** 用户保存
- **THEN** 系统 MUST 拒绝保存并标出问题字段

#### Scenario: 首次使用
- **GIVEN** 账号没有转盘配置
- **WHEN** 用户打开转盘或设置
- **THEN** 系统 SHALL 显示可编辑的默认候选且不自动覆盖其他账号

### Requirement: 多端配置收敛和账号隔离

配置 SHALL 通过现有账号级双向同步传播，离线修改 SHALL 保留待同步；设备收到新版配置时 SHALL 在下次打开转盘前刷新，编辑草稿被远端更新覆盖前 SHALL 给出提示。

#### Scenario: PC 设置后安卓查看
- **GIVEN** PC 与安卓登录同一账号
- **WHEN** PC 保存配置并完成同步，安卓完成拉取
- **THEN** 安卓 SHALL 显示相同的候选、顺序及权重

#### Scenario: 离线保存后重连
- **GIVEN** 安卓离线保存新配置
- **WHEN** 网络恢复并完成同步
- **THEN** PC 与安卓 SHALL 最终显示服务端仲裁后的同一配置

#### Scenario: 两端编辑同一配置
- **GIVEN** 编辑面板打开后另一设备更新了配置
- **WHEN** 本设备尝试保存旧草稿
- **THEN** 系统 SHALL 提示远端变更并允许重新载入或明确确认覆盖

#### Scenario: 切换账号
- **GIVEN** 设备有账号 A 的转盘配置
- **WHEN** 切换到账号 B
- **THEN** 账号 B MUST NOT 看到账号 A 的配置

### Requirement: 转盘不影响账本

抽取与配置操作 MUST NOT 创建金币、奖励、计时或用餐记录。

#### Scenario: 多次抽取
- **GIVEN** 用户连续抽取多次
- **WHEN** 检查账本和计时数据
- **THEN** 数据 SHALL 与抽取前一致
