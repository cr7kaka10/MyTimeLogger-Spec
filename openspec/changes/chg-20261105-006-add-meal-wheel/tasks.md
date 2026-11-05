## 1. 数据与同步

- [ ] 1.1 检查 `system_config` 新 key 在客户端入队、服务端推拉、账号切换中的真实路径（0 文件/0 行）；DoD：使用测试账号或隔离库确认 `meal_wheel_v1` 能往返且不串号，若被过滤则记录需改的具体文件。
- [ ] 1.2 新建转盘配置类型、默认项与读取校验（新增 `ui/src/mealWheel/config.ts`；≤50 行）；DoD：缺失/损坏配置返回默认项，非法项不能进入抽取。
- [ ] 1.3 新建配置保存与版本检查（新增 `ui/src/mealWheel/store.ts`、`ui/src/db.ts`；≤50 行）；DoD：保存进入账号库 Outbox；旧草稿遇新版配置提示冲突。
- [ ] 1.4 验证配置经 PC/安卓双向同步及离线重连（测试文件最多 3 个；≤50 行）；DoD：候选、顺序、权重最终一致且账号 B 不读到账号 A 数据。

## 2. 抽取逻辑与转盘

- [ ] 2.1 实现无偏随机数与按权重选项的纯函数（新增 `ui/src/mealWheel/selection.ts`；≤50 行）；DoD：边界与权重 1:3 的统计回归通过，结果始终在候选中。
- [ ] 2.2 建立转盘图形与指针（新增 `ui/src/components/MealWheel/MealWheelSheet.tsx`；≤50 行）；DoD：2–12 项扇区可见，明暗主题文字可读。
- [ ] 2.3 加入启动、旋转停止与结果反馈（`ui/src/components/MealWheel/MealWheelSheet.tsx`；≤50 行）；DoD：指针与文字结果一致，旋转中不重复抽取，结束可再抽。
- [ ] 2.4 在共享顶部快捷栏加入图标并接入主布局（`ui/src/components/common/PageQuickActions.tsx`、`ui/src/pages/MainLayout.tsx`；≤50 行）；DoD：PC 和安卓的快捷栏均可打开转盘且窄屏不重叠。
- [ ] 2.5 在 `App` 挂载转盘面板及关闭行为（`ui/src/App.tsx`；≤50 行）；DoD：转盘覆盖层可关闭，切账号后使用新账号配置。

## 3. 设置与验收

- [ ] 3.1 在设置页增加“转盘设置”入口（`ui/src/components/Settings/SettingsPage.tsx`；≤50 行）；DoD：PC/安卓均能进入编辑面板。
- [ ] 3.2 建立候选名称、顺序、权重输入（新增 `ui/src/components/MealWheel/MealWheelSettings.tsx`；≤50 行）；DoD：能增删改排序，限制 2–12 项。
- [ ] 3.3 加入概率预览、字段校验及保存反馈（`ui/src/components/MealWheel/MealWheelSettings.tsx`、`ui/src/mealWheel/config.ts`；≤50 行）；DoD：1:3 显示 25%/75%，无效配置拒绝保存。
- [ ] 3.4 处理远端更新草稿冲突及离线待同步提示（`ui/src/components/MealWheel/MealWheelSettings.tsx`、`ui/src/mealWheel/store.ts`；≤50 行）；DoD：远端变化时可重载或确认覆盖，离线保存后展示待同步。
- [ ] 3.5 运行逻辑、UI、同步回归和 PC/安卓构建，验证不改金币/计时账本并提交（测试文件最多 3 个；≤50 行新增测试代码）；DoD：测试及构建输出、实际跨端同步结果和提交哈希写入 `verification.md`。
