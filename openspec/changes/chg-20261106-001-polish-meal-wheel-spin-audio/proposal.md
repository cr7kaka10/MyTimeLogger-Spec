## Why

当前选餐转盘用单段 4 秒 CSS 过渡旋转，并用独立定时器宣布结果，缺少结束音效；用户反馈旋转不够丝滑。动画时间与结果时点分离，在页面掉帧、切后台或减弱动态效果时还可能不同步。

## What Changes

- PC 与安卓共享的转盘改用可控的加速、巡航、减速动画，结果只在动画实际完成后展示；取消动画和重复抽取有明确处理。
- 点击开始时准备音频播放，在指针停稳后播放短促选中音；遵守现有静音配置，播放失败不阻挡结果。
- 保持现有加权随机、扇区面积、账号配置与多端同步契约，并对 2–12 项、悬后台与减弱动态效果做回归。
- 排除项：不改服务端、配置结构、概率算法、金币与计时账本；不添加抽取历史或奖品机制。
- 回滚方案：撤销本变更中的转盘动画和音效调用，恢复上一版 `MealWheelSheet`；数据库无迁移。

## Capabilities

### New Capabilities

- `meal-wheel-feedback`: 转盘动画完成、结果提示音、可访问的减弱动态效果与中断行为。

### Modified Capabilities

无。基础 `meal-wheel` 契约由尚未归档的 `chg-20261105-006-add-meal-wheel` 定义，本变更新增独立反馈能力。

## Impact

- 现有模块：`ui/src/components/MealWheel/MealWheelSheet.tsx` 的旋转与结果生命周期、`ui/src/utils/audio.ts` 的音频准备与播放；PC Electron 和安卓 Capacitor 共用同一 UI。
- 不改 HTTP API、服务端与账号级 `system_config.meal_wheel_v1`；优先沿用现有 SVG，避免为一处动画引入新的运行时依赖。
