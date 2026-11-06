## ADDED Requirements

### Requirement: 转盘平顺旋转并在实际停稳后公布结果

PC 与安卓端 SHALL 使用加速、稳定旋转和减速阶段；结果 MUST 在动画完成且指针停在被选中的扇区后显示，不得仅凭固定计时器提前宣布。

#### Scenario: 正常旋转
- **GIVEN** 当前账号有 2–12 项有效餐食
- **WHEN** 用户点击“开始转动”
- **THEN** 转盘 SHALL 平顺旋转并停在按现有权重抽中的餐食
- **AND** 停止后文字结果 MUST 与指针指向一致，转动中 MUST 禁止重复开始

#### Scenario: 中途关闭
- **GIVEN** 转盘正在旋转
- **WHEN** 用户关闭面板或切换账号
- **THEN** 动画 SHALL 取消，且 MUST NOT 播放结束音效或在已关闭面板公布结果

#### Scenario: 减弱动态效果
- **GIVEN** 系统启用了减弱动态效果
- **WHEN** 用户点击“开始转动”
- **THEN** 转盘 SHALL 快速落在已抽中的扇区并显示一致的文字结果

### Requirement: 停稳后播放可关闭的选中音效

转盘 SHALL 在用户点击开始时准备音频，在实际停稳后播放短促选中音；现有静音配置为关闭声音时 MUST 保持静音。音频不可用 MUST NOT 阻挡抽取结果。

#### Scenario: 有声抽取
- **GIVEN** 现有音效配置允许播放且设备支持音频
- **WHEN** 转盘停在结果扇区
- **THEN** 系统 SHALL 播放一次短促选中音

#### Scenario: 静音或播放失败
- **GIVEN** 用户关闭相关音效或设备拒绝播放
- **WHEN** 转盘停稳
- **THEN** 系统 SHALL 正常显示结果且 MUST NOT 重复播放或弹出阻断提示
