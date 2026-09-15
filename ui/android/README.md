# Android 原生适配与桌面计时小组件

Android 主界面继续复用 React + TypeScript `LogicEngine`；Launcher 小组件不能承载 WebView，因而只用 Java `RemoteViews + Chronometer` 适配普通分类正计时。

## 容器边界与 SQLite bridge

Capacitor 包和 Android platform 均位于 `ui/`：APK 打包同一套 React UI、Hooks 与 `core/` TypeScript 业务逻辑，不包含 `desktop/` 的 Electron main/preload、BrowserWindow、托盘、快捷键或 IPC 实现。原生 Java 只承担 SQLite、HTTP、Keystore、生命周期、通知、浏览器、分享、键盘和系统栏等平台能力；不得复制计时、清单、习惯、奖励、学习、运动或同步规则。

`MainActivity` 只向 Capacitor 自有 WebView 注册 `MyTimeLoggerSqlite`，并在 Activity 销毁时移除。该 WebView 只能加载 APK 内的 `ui/dist` 资源；禁止远程 `server.url`、`allowNavigation` 或不受控 iframe。所有外链必须通过 Capacitor Browser 打开，不得在应用 WebView 内导航。

bridge 仅暴露同步 `open/close/execute/query`；数据库名不得包含路径，数据库位于应用私有目录。返回值仅包含结构化数据或稳定错误码，不记录或回传数据库路径、SQL 参数或凭据。

## 功能边界

- 网格按 `sort_order` 展示最多 15 个活动分类，固定 5 列；15 枚默认图标保持批准的原轮廓。
- “输入”“输出”保留原位置但统一灰色、不可点击，只能回 App 操作。
- 其他分类支持开始、同类 no-op、切换和停止；没有暂停按钮，也不复制总结或休息状态机。
- App 正在输入/输出或结构化状态时，widget 仅只读显示，不写状态或会话。

## 权威数据与补偿

- 计时状态：Capacitor Preferences 的 `mtl.runtime.timer.logic.snapshot.v1`。
- 分类、完成会话、同步 outbox：同一个 `my_time_logger.db`，不创建第二份数据库、不修改 schema。
- App/WebView ready 时命令进入 `useTimer` 串行队列；否则 Java fallback 只执行普通正计时。
- fallback 结束的会话使用 UUID，App 恢复后幂等补建 outbox，并按 commandId 消费去敏 aTimeLogger journal；widget 不控制远端 presence。

## 排障入口

- 命令与幂等：`WidgetTimerCommandReceiver.java`、`WidgetCommandStore.java`。
- 快照与有限状态机：`WidgetTimerPreferences.java`、`WidgetTimerEngine.java`。
- SQLite 与同步补偿：`WidgetTimerRepository.java`、`ui/src/platform/timerWidget.ts`。
- 渲染与分类：`TimerWidgetRenderer.java`、`TimerWidgetViewsFactory.java`。
- Launcher 不刷新时，先确认 provider 实例、Preferences 快照和 `my_time_logger.db` 表是否已由 App 初始化；不要清库或另建缓存。

私有 `atm:*` vector 仅允许老板本地私有构建，不得公开 push、发布或转交第三方。
