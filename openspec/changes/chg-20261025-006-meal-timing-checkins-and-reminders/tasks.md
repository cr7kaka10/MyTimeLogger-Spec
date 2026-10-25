## 1. 服务端 V5 规则与截止结算

- [x] 1.1 增加 V5 饮食政策生效日标记和幂等规则补齐迁移；最多修改 `server/models/server_schema.py`、`server/server.py` 两个文件、50 行。DoD：迁移日期为升级后的下一北京时间日，新三餐规则下发到现有用户 V5 计划且不覆盖自定义项。
- [x] 1.2 按 V5 政策生效日切换规则权重并保留历史评分；最多修改 `server/domain/exercise_v4_service.py`、`server/server.py` 两个文件、50 行。DoD：生效日前用旧 V5 权重，之后饮食规则分值为 11/11/11/6/6/5、训练归一到 50、身体为 0；满分奖励忽略零分身体域。
- [ ] 1.3 按单项窗口校验打卡并在截止后幂等转失败、扣币；最多修改 `server/domain/exercise_v4_service.py`、`server/server.py` 两个文件、50 行。DoD：08:30 前/12:00–13:30/18:00–19:00 边界正确，每个超时失败饮食项扣 20 金币，迟到打卡不能得分；服务端周期扫描不超过每分钟一次，既有身体记录缺失 -50 金币处罚不变。

## 2. 运动页展示

- [ ] 2.1 展示 V5 餐次窗口、单项分值和新的饮食/训练分类上限；最多修改 `ui/src/components/Exercise/ExercisePanel.tsx`、`ui/src/pages/ExercisePage.tsx`、`ui/src/utils/exerciseAuthoritativeScore.ts` 三个文件、50 行。DoD：PC 与 Android 的 V5 展示均与服务端满分配置一致，身体记录为 0 分，V4 及更早版本显示不变。

## 3. Android 本地提醒

- [ ] 3.1 增加按日期和餐次稳定排程/取消提醒的薄封装；最多修改 `ui/src/platform/mealReminders.ts`、`ui/src/platform/reminders.ts` 两个文件、50 行。DoD：五个时点和文案正确，重复排程幂等，通知权限不可用不阻断打卡。
- [ ] 3.2 接入启动、回前台、V5 切换、打卡及同步状态 reconcile；最多修改 `ui/src/bootstrap.ts`、`ui/src/hooks/useExercise.ts`、`ui/src/pages/ExercisePage.tsx` 三个文件、50 行。DoD：只为活动 V5 排程；完成餐次立即取消其剩余提醒，切换离开 V5 时清除未触发提醒。
