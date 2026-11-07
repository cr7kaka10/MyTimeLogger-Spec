## 1. 动画

- [x] 1.1 记录现有 2、6、12 项转盘的旋转与停稳表现，并确认 PC/安卓 Web Animations 支持（0 文件/0 行）；DoD：`verification.md` 写明可复现的起止时序、平台版本和回退条件。
- [x] 1.2 抽出目标角度与分段旋转计算（新增 `ui/src/mealWheel/animation.ts`、新增 `ui/src/mealWheel/animation.test.ts`；≤2 文件/50 行）；DoD：2、6、12 项及非均匀权重的指针落点测试通过。
- [x] 1.3 将固定 CSS transition 和结果定时器改为动画完成事件（`ui/src/components/MealWheel/MealWheelSheet.tsx`；1 文件/≤50 行改动）；DoD：开始/完成/取消/减弱动态效果四条路径的指针与结果一致，重复点击无第二次抽取。

## 2. 结束音效

- [x] 2.1 在用户手势内准备可复用音频并提供短促结束音（`ui/src/utils/audio.ts`；1 文件/≤50 行改动）；DoD：允许音效时结束只响一次，现有静音配置为 `none` 时无声，音频失败不抛到 UI。
- [x] 2.2 转盘接入音频准备、结束播放和取消清理（`ui/src/components/MealWheel/MealWheelSheet.tsx`；1 文件/≤50 行改动）；DoD：正常落点有声，关闭面板/切账号中断无结束音。

## 3. 验收

- [x] 3.1 在 PC Electron 与安卓模拟器检查 2、6、12 项、后台恢复、减弱动态效果和静音（0 文件/0 行）；DoD：录入实际画面与音频结果，指针、名称和提示音时点一致。
- [x] 3.2 运行转盘逻辑测试、UI 类型检查、PC/Android 构建和 OpenSpec strict，提交代码与 `verification.md`（≤1 文档/50 行）；DoD：记录命令结果、失败项和提交哈希，工作树干净。
