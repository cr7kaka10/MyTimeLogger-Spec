## ADDED Requirements

### Requirement: 测试部署明确交付 Android APK
测试部署 SHALL 从当前工作树构建 Android APK，显示产物路径、构建修订及 SHA256，并分别报告 APK 构建与目标设备安装状态。桌面 EXE 打包 SHALL 不阻止“全部部署”先生成 Android 产物。

#### Scenario: 桌面打包停滞前已生成 Android 产物
- **GIVEN** 用户选择 [1] 且服务端阶段成功
- **WHEN** 桌面 EXE 打包开始
- **THEN** 当前源码的 Android APK 已生成，日志可见其路径、修订与 SHA256

#### Scenario: 手机未连接
- **GIVEN** APK 已构建且 ADB 无处于 `device` 状态的目标
- **WHEN** 部署流程报告 Android 结果
- **THEN** 明确显示“APK 已构建、手机待安装”，并给出可使用的 APK 路径

#### Scenario: 指定设备覆盖安装
- **GIVEN** 用户明确选择安装且恰有一个处于 `device` 状态的目标
- **WHEN** 对该序列号执行覆盖安装
- **THEN** 只有安装和包核验均成功才报告“手机已更新”；失败时保留旧 App 和 APK 并报告原因

#### Scenario: 多个设备
- **GIVEN** ADB 列出多个处于 `device` 状态的目标
- **WHEN** 用户未指定唯一目标
- **THEN** 不安装任何设备，并明确提示选择目标或手工安装
