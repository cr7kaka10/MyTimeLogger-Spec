## ADDED Requirements

### Requirement: 顶部快捷操作显示选餐转盘

PC 与安卓主界面的共享快捷操作区 SHALL 显示“选餐转盘”入口，点击后 SHALL 打开转盘；在窄屏和明暗主题中入口 SHALL 保持可见、可点击且不遮挡其他关键操作。

#### Scenario: 顶部打开转盘
- **GIVEN** 用户位于计时等非设置主页面
- **WHEN** 点击顶部选餐转盘图标
- **THEN** 当前界面 SHALL 打开选餐转盘面板

#### Scenario: 安卓窄屏
- **GIVEN** 安卓屏幕宽度较窄
- **WHEN** 顶部快捷栏显示转盘入口
- **THEN** 转盘、同步状态与其他关键入口 SHALL 可操作且不重叠
