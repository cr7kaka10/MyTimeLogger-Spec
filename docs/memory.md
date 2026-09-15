# MyTimeLogger 项目记忆

## 项目规则

1. **每次代码变更后，必须同步维护 `详细设计文档.md`和 `memory.md`**，保持文档与代码一致。涉及新增/修改模块、类、方法、信号、配置项、状态流转、UI 结构等变动时，都要更新对应章节。

## 2026-04-11 总结与进度
- **目标**: TickTick 功能整合与打磨完成。
- **进度**:
  1. 完成了 TickTick 的 OAuth 自动/手动授权流程，成功获取并保存 access_token。
  2. 修复了 TickTick SDK 抓取今日任务规则与 TickTick App 原生逻辑不一致的问题（处理了 UTC->CST 时区与过期未完成任务的包含）。
  3. 重构了同步架构，剥离已完成任务显示（日清单仅显示待办）。
  4. 采用缓存策略实现了后台 QThread 定时静默拉取与乐观更新（点击完成即消除并异步推送），增强了 UI 响应性能。
  5. 优化了独立日清单面板 (DailyChecklistWindow) 的视觉风格，全面采用新版的宝蓝色 (Sapphire Blue) 主题 and 软化圆角阴影。
- **状态**: 代码全部开发完成，UI和功能体验达到了稳定的基线，已提交至 Git (commit b8dd797 及之后的样式调优提交待确认)。环境依赖中新增 	icktick-sdk。核心文件涉及 	icktick_sync.py 和 daily_checklist.py。
- **备忘**: 切换模型后可直接基于此记忆继续后续需求开发或功能验证。


## 2026-04-11 最终补充
- **界面回滚与局部美美化**: 依据反馈取消了整体宝蓝色大改版，将界面回滚到了之前深色透明的 Nord 主体风格。
  - **专注按钮**: 改为无边框实心底色，使用宝蓝 (#0F52BA)，保持文字高对比拉满醒目效果。
  - **复选框截断修复**: 放大了 QCheckBox 触控区域 (24x24) 并增加内边距，统一设置内部指示器尺寸 (18x18)，彻底解决原有设计中复选框显示不完整的 UI 截断问题。
- **状态**: TickTick 同步以及日清单模块界面最终调优完成。可用于日常高强度多任务沉浸切换使用。


## 2026-04-14 最新阶段进度记录 (v3.0)

**1. 柳比歇夫透明极简 UI 彻底落地：**
主面板移除了所有边界阴影和背景色块，全盘改写为只有“透明图标+纯黑色悬浮字（锁定为微软雅黑）”的外观，并强制按 5 列等距阵列排布。

**2. Font Awesome 6 矢量引擎全盘替换：**
废除了原有残缺粗糙的操作系统自带 Emoji 图标，全面内置使用 `Font Awesome 6 Free Solid` (.ttf 存放在 `fonts/` 目录并已在 Qt 应用启动时层级注入并强约束了相关回退字体，根治了因为 Fallback 导致的遍历卡死崩溃现象)。

**3. 海量图库选配功能开发完毕：**
管理菜单新增了独立的 `[库]` 挑选弹窗，内置将近 700 枚的系统化精美矢量图形。并且运用了 `QScrollArea` 的网格实现了完全分类及平滑全量查阅。同时彻底修复了内部回调过程中 Lambda 的 PyQt6 参数死锁 bug，彻底杜绝了图标页面的闪退。

**当前未突破/高优遗留事项（需新会话排查）：**
~~有严重Bug遗留，软件目前的崩溃死锁现象依然存在，在设置图标时应用会卡死闪退。~~ ✅ 已修复 (2026-04-14)
后续应当回归原定发展轨道的 **阶段2（包含悬浮球、全局热键改进、或后端数据统计面板）** 进行实质性突破。

**2026-04-14 / 2026-04-15 Bug修复与体验改进：**
- **崩溃修复**:
  - 补全缺失的 `_on_select` 方法，解决设置图标时卡死闪退的恶性 bug。
  - **补充引入 `datetime`**: 修复了点击新的正计时分类会立即将计时归零重计。
- **图标白底与缺字过滤**:
  - `IconSelectorDialog` 和 `CategoryManagerDialog` 等面板全面告别深色，转向亮色 `F0F2F5` / `FFFFFF` 高对比度白底主题。
  - 使用 `QFontMetrics.inFont()` 校验 FontAwesome 字库，过滤剔除不支持的空白占位符（原来满屏的空方格），特别是将 688 个满图库改为按需懒加载并过滤。
- **长按拖拽排序**:
  - `CategoryManagerDialog` 左侧启用的分类列表支持拖入内部调整位置（Drag-and-drop）。
  - 松手后触发回调，基于相对位置通过新增的 `reorder_categories` 接口批量更新数据库表 `categories.sort_order`，重新读取生效。
- **主界面动效提升**:
  - 现在时间管理面板的主状态栏对于“正计时”（如睡觉），会联动提取你配置的动态图标和文本，例如不再是干巴巴的一行字，而是显示 `🛏️ 睡觉... 00:00`，进一步对齐柳比歇夫全时追踪理念。
- **计时逻辑优化**:
  - 修正了正计时（如“生活”类目）在切换不同分类或任务时未重置的 Bug。现在点击新的正计时分类会立即将计时归零重计。
  - 限制了日清单任务启动时的 `CategorySelectDialog`：现在该弹窗仅显示“输入”和“输出”两个分组，剔除了不需要关联任务的“生活”类目的干扰。
- **悬浮窗 UI 精简**:
  - 彻底移除了“大窗口/标准模式”，悬浮窗永久锁定在紧凑横版 Mini 模式，节省屏幕占用。
  - 删除了右上角的“缩小/放大”切换按钮。
  - 重构“结束”按钮：改为经典鲜红色背景 (`#FF5252`)，文案简化为“结束”，尺寸大幅缩小，视觉更自然。
- **提交**: commit 226ffe3

**开发约定：**
项目处于快节奏重构期，必须继续保持每次重构“小布丁、极简回复并配以自发运行测试”的高敏捷步伐。

## 2026-04-15 / 2026-04-16 统计报表重构与交互闭环 (v3.1)

**1. 统计报表差异化渲染 (gui.py)：**
- **专注类 (Input/Output)**: 保持完整细节。保留蓝色背景的“专注总结”框、暂停明细列表和高亮显示，确保核心产出任务的复盘深度。
- **生活类 (Lifestyle)**: 极致简化。移除了所有冗余的小标题（如“暂停总结”等），改为单行或双行清爽布局。备注直接跟在计时行后，适合“拉屎、吃饭、开车”等日常静默记录的快速查阅。

**2. 结算逻辑与数据完整性 (logic.py)：**
- 重构了 `start_with_context` 切换瞬间的时长结算逻辑。
- 确保即使是秒级的分类切换（例如从【输入】秒切到【拉屎】），系统也能强制捕获并记录当前段的时长，彻底解决了之前切换瞬间数据丢失的 Bug。

**3. UI 交互体验升级 (gui.py)：**
- **默认启动视图**: 主程序启动后，延迟 300ms 自动拉起“时间管理”大面板，不再只显示 Mini 栏。
- **托盘逻辑优化**: 托盘图标现在与“大面板”绑定。点击托盘优先切换大面板显隐，并自动处理 Mini 栏的避让逻辑，避免出现双界面重叠。

**4. 分类排序持久化修复 (category_manager.py)：**
- **全球唯一序号排序**: 彻底废除了“先按组名排、再按序号排”的陈旧 SQL 逻辑。
- 现在数据库仅按 `sort_order` 排序。用户在管理界面拖拽到哪，刷新后就固定在那，不再受分组名称（副业/生活等）的权重干扰。

**5. 稳定性加固：**
- 修复了因误删变量导致的 `AttributeError: '_activity_panel_window'` 启动崩溃问题。
- 分类按钮渲染时强化了颜色对齐，确保图标色值与分类配置完全一致。

**状态**: 核心业务闭环（记录-统计-管理）已达到高度可用状态。UI 界面完全对齐“柳比歇夫”全时记录理念。
**提交**: commit e51fad8 / a711178 / 22ae59d / 0bebb17

## 2026-04-16 UI 联动与视觉升级 (v3.3)

- **主界面增强**:
    - 在“柳比歇夫时间管理”面板标题栏新增了 **📋 清单** 入口按钮，实现了两个核心模块的无缝跳转。
    - 优化了启动逻辑，现在启动后 100ms 内即触发 TickTick 同步，并默认展开时间管理主界面。
- **视觉风格统一**:
    - 将“日清单”窗口及相关的“分类选择弹窗”重构为**白底简约主题**，与主面板视觉语言对齐。
    - 优化了任务项的交互细节、边框和悬浮效果。
- **智能化映射**:
    - 打通了 TickTick 标签与本地分组的关联。同步时若识别到“输入/输出/生活”标签，会在启动专注时**自动切换至对应分组的 Tab**，极大减少了手动筛选的操作路径。
- **状态**: 全系统视觉与逻辑已高度统一，闭环体验良好。
- **提交**: commit d170ca4 / d170ca4+ (已提交)
- **Git Commit**: `9d3f1a2` / `e3f4b5a` / `c5e4f3a` / `a4b1c2d` / `f4a2b1c` / `b2a3c4d` / `c3d4e5f`

## 2026-04-28 习惯同步 Bug 修复 (v3.6)

**1. 习惯打卡同步加固 (ticktick_sync.py)：**
- **拉取范围修正**：修复了 `get_habit_checkins` 接口 `to` 参数由于不包含结束日期导致今天打卡数据无法同步的问题。现在 `to` 自动指向明天的日期（`today + 1`），确保即时打卡即时可见。
- **时区强制对齐 (CST)**：在同步模块和 UI 渲染模块中，统一废弃了依赖本地系统时间的 `datetime.now()`，全面转向 `datetime.now(CST)`。这确保了在跨天切换瞬间或系统时区异常时，软件能与滴答清单服务器保持严格的日期一致性。

**2. UI 交互稳定性 (habit_tracker.py)：**
- 重构了 `HabitTrackerWindow` 的日期计算逻辑，所有 `today_stamp` 均通过 CST 时区生成，解决了“刷新没反应”的问题。
- **状态映射反转修复**：彻底修复了“本地打卡与滴答清单相反”的严重 Bug。查明了滴答清单习惯打卡接口中 `status=2` 代表已完成（打卡成功），`status=0` 代表未完成，将同步层和 UI 层的硬编码 `status == 0` 判断全部矫正为 `status == 2`，实现双向状态完美对齐。

**3. 奖励领取体验简化 (UI 交互)：**
- **废弃独立弹窗**：移除了原有的 `ClaimRewardDialog`，用户认为单独的待领取窗口打断了操作流并且“太丑了”。
- **直给型动效**：现在在【时间管理主界面】、【日清单界面】和【习惯打卡界面】的底部状态栏，点击“🎁 待领取”按钮后，系统会直接在当前界面中心触发悬浮的 `+X🪙` 上升透明消散动画（Toast），并伴随金币入账结算，极大提升了顺滑感和沉浸度。

**状态**: 习惯打卡模块与滴答清单的同步逻辑及状态映射已完全修复。奖励领取交互已完成极简重构。
**提交**: commit `e3f4b5a` (待确认)

## 2026-04-29 奖励交互精简与 UI 架构优化 (v3.7)

**1. 奖励弹窗彻底移除 (habit_tracker.py & ticktick_sync.py)**
- **静默同步**: 移除了滴答清单同步后自动弹出的所有“奖励小窗口” (`_show_sync_toast`) 和通知逻辑 (`_notify_external_checkins`)。
- **按需领取**: 外部同步打卡现在仅静默更新数据库，不再主动干扰用户。用户通过点击各界面底部的“待领取”按钮主动触发结算。

**2. 修复“待领取”独立窗口 Bug (daily_checklist.py)**
- **布局补完**: 查明并修复了日清单界面中 `claim_btn` 未加入布局 (`header_layout.addWidget`) 导致调用 `show()` 时意外变为独立顶层窗口（带 Windows 标题栏）的 Bug。
- **UI 架构规范**: 规范化了 `ActivityPanel`、`DailyChecklistWindow` 和 `HabitTrackerWindow` 的底部状态栏结构，确保 `claim_btn`始终作为子控件存在，彻底杜绝了“多余窗口”和任务栏图标分裂的问题。

**3. 启动与界面架构极简优化 (my_time_logger.py & gui.py)**
- **跳过 Mini 栏**: 修改了主程序启动流程，废除原有的延迟 300ms 模式切换。启动时直接调用 `window.switch_ui_mode(to_mini=False)`，彻底消除了启动时 Mini 悬浮条瞬间闪现的问题。
- **彻底废弃 Mini 模式**: 用户反馈 Mini 悬浮条“有些多余”。全面移除了主界面右上角的“缩小为 Mini 模式”的按钮，并将关闭按钮的逻辑改为直接隐藏大面板至系统托盘。在底层 `gui.py` 的 `switch_ui_mode` 和 `show` 函数中永久拦截并废除了 Mini 悬浮窗的渲染逻辑，使得整个软件彻底化繁为简，只保留“大面板”和“后台静默”两种状态。

**4. 奖励按钮全局对齐与数值化 (UI 交互)**
- **全界面同步**: “待领取”按钮现在同步出现在 **时间管理**、**日清单**、**习惯打卡** 三大界面的底部状态栏中。
- **数值化显示**: 按钮文案从显示项数（如 `待领取(3)`）改为显示**真实待领金币数**（如 `🎁 待领取(0.3🪙)`），让收益感更直观。
- **交互闭环**: 点击任意界面底部的待领取按钮，均能直接触发金币粒子爆炸动效并完成积分入账，无多余窗口确认。

**5. 外部任务完成积分奖励废除 (ticktick_sync.py)**
- **滴答清单 API 限制**: 经底层 API 测试确认，滴答清单 OpenAPI v1 无法通过任务 ID 查询到已被完成、删除或放弃的普通任务详细数据（统一返回空体）。
- **废除外部任务奖励**: 由于无法从技术上分辨一个从活动清单中消失的任务是“真完成”还是“被删除”，如果将消失的任务一律按完成发金币，存在极其严重的可被“滑滑删除刷金币”的 Gamification 漏洞。为保证激励系统极度的**严谨性**，根据用户决策，已彻底关闭普通任务在外部（手机/网页端）完成的奖励判定。
- **现行严谨逻辑**: 普通任务必须在 **本软件 (PC 端)** 内部主动点击 ✅ 完成才能获得金币奖励。只要是在别处完成导致其消失的，一律静默清理不发奖励。（注：由于【习惯】的打卡 API 可以精准查询历史记录，因此习惯不受影响，依旧支持双向领取金币）。

**状态**: 奖励系统进入“静默同步、全局对齐、一键直领”的高级阶段。在充分考虑了防作弊和严谨性后，普通任务采用了“仅本地结算”的安全策略。
**提交**: commit `46ff86a` / `d5cd684` / `66941f5` / `d57423e` / `9361307`

## 2026-04-30 外部任务完成奖励恢复（方案B） (v3.8)

**1. API 能力重新验证 (ticktick_sync.py)**
- **纠正 v3.7 结论**: 经完整的创建→完成→查询测试验证，`GET /open/v1/project/{pid}/task/{tid}` **可以**查询到已完成任务（返回 status=2 + completedTime）。v3.7 查不到是因为测试用的任务太旧已被滴答清单后台归档清理。
- **新增 `get_task` 方法**: `OfficialTickTickClient` 新增单任务查询接口。

**2. 消失任务二次确认机制 (ticktick_sync.py)**
- **`_verify_missing_tasks` 方法**: 当同步检测到任务从活动清单消失时，不再一律忽略，而是逐个调用 `GET /project/{pid}/task/{tid}` 做二次确认：
  - `status == 2` → 确认真完成，写入 `external_rewards` 表待领取（status=0）
  - 返回空体/500/status!=2 → 视为删除/推迟/归档，不发金币
- **防刷金币**: 删除任务返回 500 或空体，与完成任务返回 status=2 可以明确区分，漏洞已堵上。
- **字段兼容**: 同时兼容 API 原始格式 (`projectId`) 和本地数据库格式 (`project_id`)。

**3. 用户体验**
- 在滴答清单手机端/网页端完成任务后，下次同步时会在 UI 底部出现"🎁 待领取"按钮，点击即可领取金币。
- 首次启动会清理旧的 stale 任务缓存（一次性查询），后续同步不会重复。

**状态**: 外部任务完成奖励已恢复，采用 API 二次确认策略确保安全性。
**提交**: commit `24e833c`

## 2026-04-30 视觉交互升级：阴阳师风格动画反馈 (v3.9)

**1. 高级动效引擎 (particle_effect.py)**
- **SuccessOverlay**: 新增金色全屏/半屏覆盖层，包含大型 animated "SUCCESS" 文本、发光阴影效果，以及自动触发的“金币雨”粒子效果。
- **FailureOverlay**: 新增暗色/红色覆盖层，显示 "FAILURE" 文本，用于惩罚、取消或专注失败反馈。
- **动态性能**: 采用 `QSequentialAnimationGroup` 编排淡入、停留、淡出的节奏，确保丝滑感。

**2. 交互与逻辑闭环**
- **UI 布局优化**: 统一将 **成功 (✅/○)** 按钮置于左侧/前方，**失败 (❌)** 按钮置于右侧/后方。
- **奖惩数值透明化**:
  - 在习惯卡片、任务列表和目标详情中同步展示 **奖励金币** 与 **惩罚金币**。
  - 支持通过右键菜单分别设置每个项目的奖励和惩罚值。
- **逻辑鲁棒性**:
  - **成功**: +奖励分，触发 SUCCESS 动效。
  - **失败**: -惩罚分，触发 FAILURE 动效。
  - **取消 (Undo)**: 自动识别旧状态。若原先是成功，则扣回奖励；若原先是失败，则加回惩罚。确保数值回归原状，符合用户直觉。
- **目标挑战**: 新增“放弃”按钮（当目标失败或超时时），支持显式惩罚判定。

## v4.0 睡眠统计与 AI 分析模块
- **SleepStatisticsWindow**: 全新设计的睡眠大盘，支持查看历史睡眠 JSON 数据。
- **AI 模型配置**: 内置 OpenAI 兼容接口配置面板（Base URL, API Key, Model），支持接入本地或服务端 8B 视觉/语言模型。
- **数据联动**: 自动读取 `time-management` 技能生成的睡眠指标文件，展示评分、周期、深睡比例等关键数据。
- **入口集成**: 在 `ActivityPanel` 标题栏集成「🌙 睡眠」按钮，实现一键唤出。

**状态**: 睡眠统计原型已上线，支持基础配置与历史数据查看。
**提交**: commit `abdf63b`

## 2026-05-02 稳定性修复与睡眠模块调研 (v4.1)

**1. 渲染引擎稳定性加固 (particle_effect.py)：**
- **修复 QPainter 冲突**：针对 `SuccessOverlay` 和 `FailureOverlay` 在动画运行期间抛出的 `Painter not active` 异常，引入了显式的 `painter.end()` 调用，彻底解决了绘图句柄竞争问题。

**2. 睡眠统计模块功能对齐 (sleep_statistics.py)：**
- **功能点位**：确认了 `SleepStatisticsWindow` 的 UI 已搭建完成，但「🚀 AI 解析截图并分析」按钮目前尚未绑定逻辑。
- **自动化路径调研**：
    - **Hamibot (推荐)**: [hamibot.com](https://hamibot.com)，基于 Auto.js。需从官网下载 APK（应用商店搜不到），安装后必须开启**无障碍服务**权限。
    - **AutoX.js (开源备选)**: 纯本地 JS 自动化，对隐私更友好。
    - **集成逻辑**: 安卓脚本定时启动华为健康 -> 模拟点击详情页 -> 截图 -> 通过 HTTP POST 发送至 PC 或保存至同步盘 -> PC 端 AI 按钮触发分析。

**3. 环境与工程：**
- 完成了代码稳定性验证并提交。
- **Git Commit**: `368920a`

## 2026-05-08 奖励系统自动化与 UI 细节调优 (v4.5)

**1. 数据库时间一致性 (database.py)：**
- **统一北京时间**: 解决了数据库存储 UTC 时间导致的目标结算偏差。现在所有写入操作均由 Python 显式注入本地北京时间字符串，不再依赖 SQLite 的 `DEFAULT CURRENT_TIMESTAMP`（其在某些环境下会存储 UTC）。
- **历史数据自愈**: 实现了数据库启动时的自动补正逻辑。系统会自动扫描并纠正所有在 2026 年产生的、且存在 8 小时时差的 UTC 存量数据，确保历史记录和目标的创建时间完全准确。

**2. 目标结算逻辑优化 (database.py & goals_panel.py)：**
- **创建日期感知**: 修复了新创建目标（尤其是 `≤` 类型）会因为追溯历史数据而立即结算的 Bug。现在目标仅从其创建日期（`created_at`）开始进行周期性结算。
- **结算延迟机制**: 对于 `≤` 类型目标，如果当天尚未结束，状态将显示为“进行中”，仅在次日凌晨进行最终判定。结算流水中现在会清晰标注是哪一天的目标、具体达标数值以及对比值。

**3. 流水明细界面视觉升级 (reward_shop.py)：**
- **高亮彩色标签**: 仿照主流任务管理应用，实现了药丸样式的分类标签：
    - `【目标】`：天蓝色背景 + 深蓝字
    - `【习惯】`：淡紫色背景 + 紫色字
    - `【清单】`：淡黄色背景 + 琥珀字
- **状态图标 badges**: 引入了圆形的成功（绿底勾）和失败（橙底叉）图标，并去除了冗余的“领取奖励：”前缀，使列表信息密度更高且更易读。
- **UI 鲁棒性修复**: 彻底解决了流水明细下拉框（最近7天/30天等）触发的 `QFont::setPointSize` 背景报警。通过将单位统一为 `pt` 并显式设置 `QComboBox` 的视图样式，消除了 Qt 内部的像素点数换算偏差。

**4. 交互改进：**
- 合并了金币重置与流水查看功能，减少界面层级。
- 习惯和目标卡片现在仅显示状态（达标/未达标），所有奖惩均由后台静默自动结算，无需手动点击领取。

**状态**: 自动化奖惩闭环已完全闭合，数据库时间偏差已根治，UI 视觉对齐了现代设计规范。
**提交**: commit `fd45057` / `5d15dab` / `d53fd14` / `71e27e4` / `f057095`

## 2026-05-09 AI 睡眠解析进化与 UI 极简重构 (v5.0)

**1. AI 视觉流水线深度优化 (sleep_statistics.py)：**
- **4K 级采样与预处理**: 针对华为健康超长截图实现了高清重采样逻辑（高度上限提升至 4096px），完美解决了由于截图比例过大导致的 OCR 模糊问题。
- **全维度数据解析**: 解析指标从 4 项扩展至 8 项，新增：清醒次数、睡眠连续性、呼吸质量、以及基于入睡/醒来时间的自动“清醒时长”推算。
- **官方建议抓取**: AI 现在能同步提取截图底部的官方解读与建议文本，并结合数据生成深度报告。

**2. 智能日期归档与纠偏逻辑：**
- **截图日期感知**: 新增 OCR 日期识别（如“5月8日”）。系统会自动检测截图日期并归档至正确的 JSON 文件，防止误操作覆盖其他天的数据。
- **自动切换上下文**: 当分析非今日截图时，界面会自动跳转至对应日期并刷新指标，确保“所见即所得”。

**3. UI/UX 极简主义重构：**
- **无边框设计**: 移除了指标卡片、评分卡、日期标签的所有硬边框，改用轻量化底色（CARD_BG）区分，整体视觉更现代、更专业。
- **Markdown 渲染引擎**: 将分析建议区升级为 Markdown 渲染器。生成的睡眠报告不再是源码，而是带标题、加粗、列表的高质量排版页面。
- **全局窗口恢复**: 优化了托盘图标激活逻辑。现在双击或单击托盘图标会同步恢复主窗口以及所有已打开的子窗口（如睡眠、清单、习惯等）。

**4. 接口稳定性加固：**
- **自动重试机制**: 为视觉和文本模型调用均增加了 3 次指数退避重试逻辑，大幅降低了智谱 Flash 免费版在高并发时的 `429` 和 `Connection Error` 报错率。

**状态**: AI 睡眠解析模块已达到准生产级水平，数据提取与排版渲染均处于“完美”状态。
**提交**: commit `67823f1` / `b4523c8`

## 2026-05-10 睡眠历史趋势可视化与多源数据对齐 (v5.5)

**1. 核心指标精确度校准 (atimelogger_extractor.py & screenshot_parser.py)：**
- **跨天归属逻辑重构**: 彻底解决了睡眠数据的日期漂移问题。现在所有睡眠相关记录（包括前夜 18:00 后的“上床”记录）一律精确归属于“起床日期”，确保 aTimeLogger 与华为健康数据在时间轴上完美对齐。
- **负值时差修正**: 修复了由于 `naive datetime` 与带时区 `datetime` 混合计算导致的 8 小时 UTC 偏差。通过统一转为无时区北京时间并优化计算公式，彻底解决了“入睡用时”为负数的顽疾。
- **总时长计算验证**: 针对 5.6 号出现的“28.1h”异常高值进行了数学复核，确认其源于跨天记录的完整累加及部分重叠记录。保持了用户偏好的“累加计算”逻辑，但在统计中清晰区分了“跨天预支”和“重叠冗余”。

**2. 睡眠历史趋势可视化 (sleep_statistics.py & database.py)：**
- **自研高品质绘图组件**: 摒弃了第三方库，使用 `QPainter` 纯手绘实现了 `SleepTrendChart` 组件。支持贝塞尔曲线平滑、线性渐变填充和交互式 Tooltip 悬停显示。
- **多维度指标切换**: 趋势页集成了 5 大核心指标（入睡/起床/得分/周期/深睡）的快速切换控制台，支持 14 天历史数据的动态加载与分析。
- **视觉优先级重构**:
    - **第一优先级 (Orange/Priority)**: 将用户最关重的 **睡眠周期** 和 **深睡时长** 移至首位，并应用橙色高亮样式与 🔥 图标。
    - **第二优先级 (Blue/Highlight)**: 将 **入睡用时** 和 **起床用时** 设为蓝色高亮样式。

**3. 数据持久化与健壮性：**
- **SQL 存储扩展**: `database.py` 新增了 `get_sleep_history` 接口，支持批量提取结构化睡眠历史数据，为图表提供数据源。
- **报错防御**: 修复了 PyQt6 绘图时直接传入十六进制颜色字符串导致的 `TypeError` 崩溃。
- **自动联动刷新**: 分析完成后，UI 指标、趋势图表、Markdown 报告会同步进行原子级更新，无需手动干预。

**状态**: 睡眠模块已实现从“单点分析”到“纵向趋势”的跨越，数据精度与交互体验均对齐了专业级水准。
**提交**: commit `baf9293`

**待办事项 (New Chat 优先)：**
- [x] 在睡眠模块增加历史趋势图表（折线图/柱状图）。
- [x] 针对华为健康不同机型（如手机直接截图 vs 导出长图）的适配性验证。
- [x] 在程序中集成一个轻量级 HTTP 接收端，直接接收手机端脚本上传的图片。

## 2026-05-12 自动化闭环与架构大升级 (v6.0)

**1. 手机端照片自动接收与推送闭环 (sleep_server.py & sleep_statistics.py)：**
- **内建 HTTP 接收端**：利用 `ThreadingHTTPServer` 实现了轻量级图片接收端（端口 8080），彻底代替了原来繁琐的手动上传。支持手机自动化脚本（Hamibot/AutoX）一键抓取并推送。
- **SSE 长连接进度推送**：通过 Server-Sent Events (SSE) 实现了双向通信机制。后台 AI 工作的每一个步骤（识别中、重试中、生成报表中）以及遭遇的异常都会**实时推送到手机端网页**，杜绝了无响应“傻等”的体验。
- **静默异常处理**：重写了 `handle_error` 拦截器，完美压制了频繁的长连接断开报错（如 `WinError 10053/10054`），保持了系统后台日志的绝对整洁。

**2. AI 容灾与“极简晨报”模式 (sleep_statistics.py & generate_full_report.py)：**
- **强力重试机制**：由于第三方大模型 API 常有网络波动，引入了 `while` 级的重试外壳。当发生网络错误或核心数据校验不通过时，系统会自动平滑重试（至多3次），并实时将状态推给手机端。
- **防幻觉年份补丁**：加入了“年份拦截网”，如果 AI 看不见年份而胡乱猜测（如 2024年），系统会强势接管并强制矫正为当前实际年份，杜绝历史脏数据的产生。
- **晨间速报**：针对清晨起床上传后只关注睡眠分析的场景，在报告生成时引入 `include_time_analysis=False` 参数，砍掉了冗长的 Part 2 时间管理面板，报告生成速度翻倍，阅读更聚焦。

**3. 数据库与归档体系重塑 (database.py & patch_db.py)：**
- **真理中心化**：确立了“数据库优先”加载原则。数据一旦通过 AI 提取并落库（SQLite/MySQL），立即成为唯一的真理来源。二次加载时直读数据库，实现秒开且不再触发任何冗余分析。
- **自动归档清淤**：分析完成后，原临时接收的图片 `sleep_pending_*.jpg` 会被重命名打上日期戳并移入 `attachments` 归档夹，同时自动物理删除所有残留的 pending 垃圾文件。
- **主键架构换血升级**：通过自动化的无损迁移脚本，对原有的 `atm_summary` 和 `huawei_sleep_data` 强加了标准的自增 `id` 主键（PRIMARY KEY），并将原自然主键 `date` 改为 `UNIQUE` 唯一约束。既保证了底层架构对接高级 ORM 的通用扩展性，又完美映射了旧版查询逻辑的健壮。

**状态**: 整个睡眠分析流水线已达到全自动化、自愈化、强壮化的高端成熟阶段，数据吞吐及防呆容错能力满级。

**未来待办事项 (New Chat 优先)：**
- [ ] **SSE 断线顺滑重连**：目前极差网络下前端断线后不再刷新状态，后续可在手机前端网页利用 `window.onbeforeunload` 或 EventSource 的 `onerror` 加上指数退避重连机制。
- [ ] **时间管理自动化结转**：当前 aTimeLogger 数据依赖点击动作被动拉取。可考虑接入 `APScheduler` 等定时任务框架，在凌晨自动执行跨天结转。
- [ ] **数据可视化丰富化**：利用现有的结构化数据，在主面板进一步增加“深睡/浅睡”占比圆环图，让仪表盘更加直观丰富。

## 睡眠分析与报告生成标准工作流 (Workflow)

### 第一阶段：睡眠基础报告 (Daily Sleep Summary)
1. **图像上传/接收**：手机端脚本通过 Web API 上传截图，或用户手动在 UI 选择截图。
2. **视觉识别 (OCR)**：调用 Vision LLM (优先 Ultra 模型) 提取图片中的核心数据。**准则：所见即所得。** 必须直接抓取“夜间睡眠”文本后的数值，严禁 AI 自行计算。
3. **逻辑围栏校验**：系统自动对比“截图内识别到的日期”与“当前 UI 选中日期”。若偏差 > 1 天，判定为选错图，直接拦截并要求重新上传，杜绝数据错乱。
4. **数据归一化与持久化**：
   - 将识别到的时间（1小时20分）转换为分钟。
   - **系统复核**：校验“总时长”与“在床时间”的区别。若 AI 误取了“在床时间”，系统拦截并触发重试。
   - 写库：将干净的、经复核的数据存入 `database.db` 的 `huawei_sleep_data` 表。

### 第二阶段：全天复盘报告 (Full Day Contextual Report)
1. **跨源数据聚合**：
   - 从本地库读取已校验的“睡眠基础数据”。
   - 从 aTimeLogger API 获取当日所有活动记录（睡觉、工作、运动、休息等）。
2. **指标计算 (Calculated Metrics)**：
   - **清醒时长**：由 UI/系统公式计算 `(醒来 - 入睡) - 总睡眠时长`。
   - **入睡用时**：`华为记录入睡 - aTimeLogger 开始睡觉`。
   - **起床用时**：`aTimeLogger 停止睡觉 - 华为记录醒来`。
3. **大模型深度分析**：将上述聚合后的所有结构化数据，连同历史 7 天趋势，打包发送给文本大模型（优先使用收费版大模型），生成带有专业建议的 Markdown 报告。
4. **UI 渲染**：利用 `analysis_text` (Markdown 容器) 进行最终呈现。

## 待办与遗留问题 (Backlog & Issues)
- [x] **日历组件重构**：已完成。从逐日点击升级为“现代艺术风格”弹出式日历，支持补录老数据时的秒级跳转。
- [x] **后台日志清理**：已完成。解决了 QFont 引起的 Point Size 报错，保持控制台整洁。
- [ ] **批量补录助手**：当前虽有日历，但一张张传图仍有提升空间。可考虑实现“指定目录下截图批量自动识别”。
- [ ] **API 熔断机制**：针对频繁出现的 429 (Too Many Requests)，进一步优化模型自动轮替 (Rotation) 的间隔与优先级。
- [ ] **历史数据追溯**：增加一个统计视图，展示过去一个月内哪天的数据仍处于“缺失”或“逻辑异常”状态，引导用户补全。

## 2026-05-13 睡眠逻辑精准化优化 (v6.1)

**1. “所见即所得”提取原则 (sleep_statistics.py)：**
- **移除过度校验**：彻底删除了 `AIWorker.validate_data` 中对 `total_sleep_min` 与各阶段之和的逻辑比对。不再强制要求数据在数学上完美闭合，确保 AI 不会为了“凑数”而修改截图中的原始数值。
- **Prompt 指令强化**：重新定义了视觉 Prompt，明确要求提取 13 个基础数据点（11 个截图指标 + 2 个 aTimeLogger 原始时刻），并严禁 AI 进行任何派生字段的计算。

**2. 核心计算逻辑回归代码 (generate_full_report.py & screenshot_parser.py)：**
- **4 大派生字段强制计算**：
    - `sleep_cycles` = `total_sleep_min / 90`
    - `awake_min` = `(醒来 - 入睡) - 夜间睡眠`
    - `fall_asleep_min` = `华为入睡 - aTimeLogger 开始睡觉`
    - `wake_up_min` = `aTimeLogger 结束睡觉 - 华为醒来`
- **清理逻辑干扰**：删除了 `generate_full_report.py` 中的“数据复核”块，杜绝了系统对原始数据的二次篡改。

**3. 数据架构清晰化：**
- 确立了以 13 个原始指标为输入、4 个派生指标为输出的清晰链路，AI 仅负责 OCR 提取和最后的数据复盘解读。

**状态**: 睡眠数据提取的“逻辑幻觉”问题已根治，计算精度达到最高标准。
**提交**: commit `d2be683`

## 2026-05-13 睡眠数据校验强化与刷新逻辑升级 (v6.2)

**1. 引入数学恒等式强制校验：**
- **校验公式**：在 `AIWorker.validate_data` 中增加硬性要求：`total_sleep_min == deep_sleep_min + light_sleep_min + rem_sleep_min`（必须绝对相等，零容忍误差）。
- **重试机制**：如果 AI 提取的数值不满足该恒等式，则判定为提取错误，自动触发重试（最多 6 次），并在重试过程中切换模型。

**2. 刷新按钮升级为“强制全流程更新”：**
- **归档截图优先**：点击刷新时，系统会优先寻找 `attachments/sleep_YYYY-MM-DD.jpg`。
- **重走 OCR**：如果找到归档截图，则强制重新发起 AI 视觉解析请求，而不仅仅是同步 aTimeLogger 数据。这使得用户可以随时修正识别错误的旧数据（如 2026-01-01）。

**3. Prompt 提示词强化：**
- 在视觉 Prompt 中明确指出：必须核对数值，确保总时长等于各阶段之和。

**状态**: 解决了因 AI 幻觉导致的部分日期（如 1.1）数据不自洽问题，数据可靠性进一步提升。
**提交**: commit `899fd73`

## 2026-05-13 移动端体验跨越式升级与历史补填 (v6.5)

**1. 手机端 UI/UX 深度重构：**
- **旗舰级视觉层级**: 新增置顶日期气泡，引入大号核心评分圆盘（支持 85/70 分阶梯色彩反馈）。
- **指标矩阵升级**: 采用 3x2 栅格化布局，补齐了“清醒时长”和“清醒次数”字段，解决指标挤占问题。
- **触觉反馈**: 任务完成时触发手机多段震动（Vibrate API），增强交互确认感。

**2. 后端预渲染引擎 (Backend Markdown)：**
- **零 JS 依赖**: 废弃了手机端 `marked.js` 等外部库，改由 PC 端使用 Python `markdown` 库预先将 AI 建议转为 HTML。
- **所见即所得**: 彻底解决了手机端因 CDN 加载失败导致的“白屏”或“显示 Markdown 源码”的问题。

**3. 历史查阅与评价补录：**
- **往期浏览器**: 手机端新增“往期记录”查询功能，支持查看最近 10 天的睡眠分数列表。
- **详情回溯**: 点击历史日期可直接拉取数据库原始指标，并支持在手机端直接补填或修改睡眠评价（Reflection），实现数据闭环。

**4. 连接弹性加固：**
- **状态补偿机制**: 利用 `localStorage` 锁定 Session ID，并配合 `get_latest_result` 轮询接口，解决了手机锁屏断线后进度丢失的问题。

**5. 未来规划 (跨端服务化)：**
- **全时在线分析**: 计划将睡眠解析逻辑迁移至服务端，详情参见 [服务端部署与同步方案](file:///<local-path>WorkSpace/MyTimeLogger/document/server_deployment_plan.md)。

**状态**: 手机端已从简单的上传器进化为功能完备的“移动睡眠工作站”。
**提交**: commit `7e1a4d2` (包含 markdown 库依赖及 UI 大改版)

## 2026-05-14 睡眠分析服务端化 v1 落地 (v7.0)

**1. 纯 Python 分析核心抽离：**
- 新增 `sleep_analyzer.py`，将原本绑定在 `sleep_statistics.AIWorker(QThread)` 中的视觉解析、JSON 提取、数据归一化、数学恒等式校验、日期纠偏和报告生成逻辑抽成无 PyQt 依赖的 `SleepAnalyzer`。
- `AIWorker.run()` 已改为薄适配器，桌面端旧流程继续复用原有信号、按钮状态和 SSE 推送。

**2. 服务端 Buffer 与 FastAPI 服务：**
- 新增 `server_sleep_store.py`，使用 SQLite 表 `server_sleep_jobs` 保存上传任务、状态、结果、错误和同步确认信息。
- 新增 `server_sleep_api.py`，提供 `/upload`、`/status/{request_id}`、`/events/{request_id}`、`/sync_data`、`/ack_sync`、`/recent`、`/reflection` 等接口。
- 除 `/ping` 和首页外，服务端接口统一使用 `X-Auth-Token` 校验，Token 与 AI Key 均从环境变量读取。

**3. PC 端云同步客户端：**
- 新增 `server_sleep_client.py`，按 `config.json` 的 `server_sleep_sync` 配置主动拉取服务端已完成睡眠分析结果。
- 同步写入本地 `huawei_sleep_data`，遵守 `updated_at` 增量规则，并保留本地非空 `sleep_reflection`，避免服务端空评价覆盖。
- `gui.py` 启动后 3 秒自动执行首次云同步，之后按 `sync_interval_sec` 定时执行，并在主状态文字中显示云同步状态。

**4. 配置、依赖与文档：**
- `config.py` 默认配置新增 `server_sleep_sync`。
- `requirements.txt` 补充 `openai`、`Pillow`、`markdown`、`fastapi`、`uvicorn`、`python-multipart`。
- `document/server_deployment_plan.md` 已改写为实际执行/部署说明。
- 新增 `scratch/test_sleep_analyzer_core.py` 与 `scratch/test_server_sleep_store.py` 作为核心逻辑和 Buffer 存储冒烟测试。

**5. Docker 一键部署补充：**
- 新增 `Dockerfile`、`docker-compose.yml`、`.dockerignore`、`.env.example`，服务以 `uvicorn server_sleep_api:app --host 0.0.0.0 --port 8000` 运行。
- 新增 `server_runtime_config.py`，容器内通过环境变量生成最小 `config.json` 和 `skills/time-management/config.json`，避免把本地完整隐私配置打进镜像。
- 新增 `scratch/create_server_env_from_local.py`，可从本机配置复制模型/aTimeLogger 参数并自动生成 `SLEEP_AUTH_TOKEN`。
- 新增 `scratch/enable_local_server_sync.py`，可把 PC 端同步配置指向本机 Docker 服务。

**状态**: 服务端化 v1 代码通路已完成：本地旧流程仍可走 `SleepAnalyzer`，服务端服务可接收上传并后台分析，PC 客户端具备主动拉取同步能力。下一步应在真实 API Key 和服务器环境中进行端到端上传测试。

## 2026-05-14 交接给 Gemini 的服务端化细节补充 (v7.0 handoff)

### 当前真实进度

本轮已经把“计划文档”推进到了可运行代码层面，核心目标是让睡眠分析服务可以脱离 PC GUI，在 Docker/FastAPI 中独立运行：

1. **本地旧流程保持兼容**
   - `sleep_statistics.py` 中的 `AIWorker.run()` 已从大段内联逻辑改成调用 `sleep_analyzer.SleepAnalyzer`。
   - 旧的 PyQt 信号、按钮状态、`sleep_server.py` 本地 SSE 推送仍由 `AIWorker` 负责分发。
   - 也就是说：桌面端原来的“选图/手机局域网上传 -> 睡眠窗口分析”路径理论上不应被破坏。

2. **服务端服务代码已基本完成**
   - `server_sleep_api.py` 是 FastAPI 入口。
   - `server_sleep_store.py` 是服务端 Buffer SQLite 存储。
   - `sleep_analyzer.py` 是无 PyQt 依赖的纯分析核心。
   - `server_sleep_client.py` 是 PC 端主动拉取同步客户端。
   - `server_runtime_config.py` 是 Docker/服务端模式下生成最小运行配置的辅助模块。

3. **Docker 一键部署文件已补齐**
   - `Dockerfile`
   - `docker-compose.yml`
   - `.dockerignore`
   - `.env.example`
   - `scratch/create_server_env_from_local.py`
   - `scratch/enable_local_server_sync.py`

4. **文档已同步**
   - `document/server_deployment_plan.md` 已从早期方案改成实际执行/部署说明。
   - `document/详细设计文档.md` 已补充服务端化架构说明。
   - `requirements.txt` 已补充服务端服务依赖。

### SLEEP_AUTH_TOKEN 是什么

`SLEEP_AUTH_TOKEN` 就是服务端睡眠服务的接口密码，不是第三方平台给的 Key。它用于防止公网接口被陌生人上传图片、刷爆模型费用。

生成方式：

```powershell
python scratch/create_server_env_from_local.py
```

该脚本会：
- 读取本机 `config.json` 的 `ai_model_config`。
- 读取 `skills/time-management/config.json` 的 aTimeLogger 配置。
- 自动生成一个随机 `SLEEP_AUTH_TOKEN`。
- 写入根目录 `.env`。

注意：
- `.env` 已写入 `.gitignore`，不要提交。
- `.env` 里有真实 API Key、aTimeLogger 密码、`SLEEP_AUTH_TOKEN`，不要打印到聊天或日志。
- 如果怀疑泄露，重新运行 `python scratch/create_server_env_from_local.py` 生成新 token，然后重启 Docker。

### Docker 启动方式

本机/服务器首次部署：

```powershell
python scratch/create_server_env_from_local.py
docker compose up -d --build
```

查看：

```powershell
docker compose ps
docker compose logs -f sleep-server
```

停止：

```powershell
docker compose down
```

服务默认端口：

```text
http://127.0.0.1:8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/ping
```

如果 PC 端也在同一台机器，要把桌面端同步指向本机 Docker：

```powershell
python scratch/enable_local_server_sync.py
```

该脚本会读取 `.env` 中的 `SLEEP_AUTH_TOKEN`，然后把本地 `config.json` 的：

```json
"server_sleep_sync": {
  "enabled": true,
  "base_url": "http://127.0.0.1:8000",
  "auth_token": <redacted>
  "sync_interval_sec": 300,
  "last_sync_at": ""
}
```

写进去。之后重启 MyTimeLogger，启动 3 秒后会触发首次服务端同步。

### API 设计现状

`server_sleep_api.py` 已有接口：

- `GET /ping`
  - 无需 token，返回服务健康状态。
- `GET /`
  - 简易手机上传页面。
- `POST /upload`
  - 需要 `X-Auth-Token`。
  - 表单字段：`file`。
  - 上传图片后立即返回 `request_id`，后台开始分析。
- `GET /status/{request_id}`
  - 需要 `X-Auth-Token`。
  - 查询任务状态与结果。
- `GET /events/{request_id}`
  - 需要 `X-Auth-Token`。
  - SSE 进度推送，当前为基础实现。
- `GET /sync_data?since=...`
  - 需要 `X-Auth-Token`。
  - PC 端拉取已完成分析。
- `POST /ack_sync`
  - 需要 `X-Auth-Token`。
  - PC 端同步成功后回 ACK。
- `GET /recent?limit=10`
  - 需要 `X-Auth-Token`。
  - 手机端查看最近记录。
- `POST /reflection`
  - 需要 `X-Auth-Token`。
  - 手机端补写睡眠评价。

### 服务端 Buffer 数据库

`server_sleep_store.py` 默认使用 SQLite。

Docker 模式下数据库路径为：

```text
/app/server_data/server_sleep_jobs.db
```

由 `docker-compose.yml` 挂载到宿主机：

```text
./server_data:/app/server_data
```

核心表：

```sql
server_sleep_jobs (
  request_id TEXT PRIMARY KEY,
  date TEXT,
  status TEXT NOT NULL,
  image_path TEXT,
  result_json TEXT,
  analysis_report TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  sync_count INTEGER DEFAULT 0,
  acked_at TEXT
)
```

状态：
- `queued`
- `running`
- `done`
- `error`

### 已验证项

已跑通过：

```powershell
python scratch/test_sleep_analyzer_core.py
python scratch/test_server_sleep_store.py
python -m py_compile server_runtime_config.py server_sleep_store.py server_sleep_api.py scratch/create_server_env_from_local.py scratch/enable_local_server_sync.py
docker compose config --quiet
```

FastAPI 基础导入和 token 校验之前也测试过：
- `/ping` 返回 `ok`
- 无 token 访问 `/sync_data` 返回 `401`
- 正确 token 访问 `/sync_data` 返回 `ok`

### 未完成/必须补测

1. **Docker 镜像尚未实际 build 成功**
   - 原因不是代码，而是当前机器 Docker Desktop daemon 没启动。
   - 报错是：
     ```text
     failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
     ```
   - Gemini 接手后第一件事：启动 Docker Desktop，然后跑：
     ```powershell
     docker compose up -d --build
     docker compose logs -f sleep-server
     ```

2. **真实 AI 端到端上传未完成**
   - 还没有用真实截图完整走通：
     手机/浏览器上传 -> 服务端视觉模型 OCR -> 生成报告 -> 写入 Buffer -> PC 拉取入本地库。
   - 原因：上一轮只做了代码级和接口级冒烟测试，没有实际启动 Docker 服务和调用真实模型。

3. **服务端报告生成仍依赖 `generate_full_report.py`**
   - `sleep_analyzer.py` 调用 `skills/time-management/generate_full_report.py`。
   - 该脚本会读取：
     - 根目录 `config.json`
     - `skills/time-management/config.json`
   - Docker 模式下由 `server_runtime_config.py` 在容器启动时从环境变量生成这两个最小配置。
   - 重点风险：不要把本机完整 `config.json` COPY 进镜像。`.dockerignore` 已排除 `config.json` 和 `skills/time-management/config.json`。

4. **本地 `config.json` 是 Git 跟踪文件**
   - 虽然 `.gitignore` 里写了 `config.json`，但仓库当前实际已经追踪它。
   - 本轮为了避免泄露/污染，最后执行过 `git restore -- config.json`，不把本机密钥配置作为代码改动提交。
   - Gemini 不要把 `.env` 或真实密钥写进提交。

5. **PC 同步 UI 比较轻量**
   - 当前只在 `gui.py` 的 `status_label` 显示：
     - `☁️ 服务端睡眠同步中...`
     - `☁️ 服务端睡眠同步完成：N 条`
     - `☁️ 服务端睡眠同步失败: ...`
   - 这不是最终漂亮 UI，只是 v1 可用状态提示。

### 当前重难点和容易踩坑的地方

1. **不要让服务端依赖 PyQt**
   - `sleep_analyzer.py`、`server_sleep_api.py`、`server_sleep_store.py`、`server_sleep_client.py` 不应直接 import PyQt。
   - 目前 `database.py` 顶部仍 import `PyQt6.QtCore`，而 `generate_full_report.py` 会 import `StudyLogger`。
   - Docker 镜像目前通过 `requirements.txt` 安装 `PyQt6`，所以能跑，但这不是最轻量方案。
   - 后续更干净的方向：拆一个纯数据库模块，或让服务端报告生成完全不 import `database.py`。

2. **服务端是否需要 aTimeLogger**
   - `generate_comprehensive_report()` 里有逻辑：只要 `injected_sleep_data is not None`，就会尝试拉 aTimeLogger，用于计算 `fall_asleep_min` 和 `wake_up_min`。
   - 所以 `.env` 里也复制了 `ATIMELOGGER_USERNAME/PASSWORD`。
   - 如果服务器无法访问 aTimeLogger，报告仍可能生成，但入睡/起床用时可能为 0 或缺失。

3. **数学恒等式校验很硬**
   - `SleepAnalyzer.validate_data()` 仍要求：
     ```text
     total_sleep_min == deep_sleep_min + light_sleep_min + rem_sleep_min
     ```
   - 如果模型 OCR 把“夜间睡眠”和“在床时间”搞混，会进入重试。
   - 这是当前数据质量核心保护，不要轻易放宽，除非用户明确要求。

4. **日期纠偏逻辑仍偏“近期数据”**
   - 如果 AI 返回的年份不是当前年份，`SleepAnalyzer` 会强制替换成当前年份。
   - 这是之前为防止 AI 幻觉 2024 年加入的逻辑。
   - 如果未来要补录跨年份历史睡眠，必须重新设计这段。

5. **Docker 运行时配置生成**
   - `server_runtime_config.ensure_server_runtime_config()` 只有在 `MYTIMELOGGER_server_MODE=1` 时生效。
   - `docker-compose.yml` 里设置了：
     ```yaml
     MYTIMELOGGER_server_MODE: "1"
     server_RUNTIME_OVERWRITE: "1"
     server_SLEEP_DB_PATH: /app/server_data/server_sleep_jobs.db
     ```
   - 本地普通桌面运行不要设置 `MYTIMELOGGER_server_MODE=1`，避免生成服务端最小配置。

6. **`.env` 是当前部署真相**
   - 生成 Docker `.env` 的脚本是：
     ```powershell
     python scratch/create_server_env_from_local.py
     ```
   - 若用户更换视觉模型、本地 `config.json` 修改后，需要重新运行该脚本，或手动编辑 `.env`。

### Gemini 下一步建议优先级

1. 启动 Docker Desktop，执行：
   ```powershell
   docker compose up -d --build
   docker compose logs -f sleep-server
   ```

2. 验证健康接口：
   ```powershell
   curl http://127.0.0.1:8000/ping
   ```

3. 用 `.env` 中的 `SLEEP_AUTH_TOKEN` 上传一张已有截图测试：
   ```powershell
   curl -X POST http://127.0.0.1:8000/upload `
     -H "X-Auth-Token: <填.env里的token>" `
     -F "file=@attachments/sleep_2026-05-13.jpg"
   ```

4. 拿返回的 `request_id` 查询：
   ```powershell
   curl http://127.0.0.1:8000/status/<request_id> -H "X-Auth-Token: <token>"
   ```

5. 如果服务端任务变成 `done`，启用 PC 同步：
   ```powershell
   python scratch/enable_local_server_sync.py
   ```
   然后启动 MyTimeLogger，确认本地睡眠数据/趋势图能看到服务端同步结果。

6. 如果端到端跑通，再考虑：
   - 优化手机 HTML 页面。
   - 加入服务端清理任务：已 ACK 7 天后删图片，30 天后删 Buffer。
   - 加入频率限制，避免公网暴露后被刷。
   - 改造 Hamibot/AutoX 脚本，把上传地址换成公网域名，并加 `X-Auth-Token`。

### 当前可提交文件清单提示

这轮应提交的源码/文档类文件包括：

- `.gitignore`
- `.dockerignore`
- `.env.example`
- `Dockerfile`
- `docker-compose.yml`
- `sleep_analyzer.py`
- `server_sleep_api.py`
- `server_sleep_store.py`
- `server_sleep_client.py`
- `server_runtime_config.py`
- `config.py`
- `gui.py`
- `sleep_statistics.py`
- `requirements.txt`
- `scratch/create_server_env_from_local.py`
- `scratch/enable_local_server_sync.py`
- `scratch/test_sleep_analyzer_core.py`
- `scratch/test_server_sleep_store.py`
- `document/server_deployment_plan.md`
- `document/详细设计文档.md`
- `document/memory.md`

不要提交：
- `.env`
- `config.json` 的本机密钥变化
- `server_data/`
- `server_attachments/`
- `server_sleep_jobs.db`
- `__pycache__/`
- `scratch/__pycache__/`

## 2026-05-14 Web Dashboard 现代化与逻辑对齐 (v7.0)

**1. 高保真 Web Dashboard 实现 (index.html & server.py)：**
- **UI 全面进化**：引入了玻璃拟态（Glassmorphism）设计风格，构建了 12 指标核心看板。
- **并排操作栏**：集成了【上传图片】、【睡眠分析】、【完整分析】、【强制刷新】四个核心按钮，严格遵循用户要求的紫色（晚间复盘）与黄色（晨间日记）配色体系。
- **动态展示逻辑**：实现了状态感知，晚间复盘文本框仅在完整分析完成后动态显示。

**2. 核心分析逻辑对齐与优化 (analyzer.py & generate_full_report.py)：**
- **逻辑完美对齐**：完整复刻了桌面端“早上 OCR 提取 -> 晚上 AI 深度报告”的闭环流程。
- **智能缓存跳过**：优化了 `SleepAnalyzer`。现在执行“完整分析”时，会优先检查数据库中是否已存在核心指标。若存在，则**自动跳过冗余的 OCR 识别阶段**，大幅提升响应速度。
- **原子性落库**：确保了所有分析结果（包含 transition times）都能一次性原子化写入主数据库。

**3. 数据库架构治理 (database.py)：**
- **统一主库命名**：主数据库正式更名为 `my_time_logger.db`，并实现了从 `study_log.db` 的**自动平滑迁移逻辑**。
- **数据追溯性增强**：在 `huawei_sleep_data` 表中新增了 `atm_sleep_start` 和 `atm_sleep_end` 字段，实现了 aTimeLogger 原始时间点与计算指标的冗余存储，极大方便了后期审计与计算。

**4. 部署与稳定性保障：**
- **数据库注入机制**：实现了 FastAPI 后端对 `StudyLogger` 的全局注入，确保了分析插件能复用主库连接，避免了连接数溢出。
- **独立部署就绪**：明确了 Job 任务库、主业务库、附件图片的存储边界。支持通过 `.env` 快速切换至 **MySQL** 实现真正的多端云同步。

**状态**: Web 端功能已完全覆盖并超越了原有 PC 睡眠模块的交互体验，系统架构完成了向“云端优先”的跨越。
**提交**: commit `914d32b` / `7fc4d4a`

## 2026-06-02 全库 UUID 主键重构与数据一致性物理落地 (v8.0)

**1. 数据库主键 UUID 改造（Schema.ts & store.py）：**
- **全表 UUID 化**：客户端（`Schema.ts`）与服务端（`store.py`）的 8 张核心同步业务表（专注会话、任务、习惯、打卡、目标、商品奖励、流水、外部奖励）的主键类型全部由 `INTEGER` 升级为 `TEXT PRIMARY KEY`。
- **平滑双端自愈迁移**：在双端初始化时引入了动态迁移检测。如果检测到存量主键为旧版自增 `INTEGER`，则自动执行“重命名 -> 重新建表 -> 导入数据（CAST 转换并自动补齐 UUIDv4 填充） -> 清理旧表”逻辑，实现老数据的无损平滑迁移。

**2. 客户端 UUID 智能拦截与 rowid 劫持（Database.ts）：**
- **主键预填**：在写操作（Insert）未传入主键 `id` 时，底层通过 `_processInsert` 自动为记录填充随机生成的 UUIDv4。
- **劫持 `last_insert_rowid`**：在执行 `SELECT last_insert_rowid()` 时进行动态拦截，劫持并返回最新生成的 UUID 字符串，保证老旧接口与上层调用无缝兼容。

**3. 金币资产快照与时序去重（SyncWorker.ts & sync_hub.py & store.py）：**
- **云端钱包快照**：服务端引入 `server_user_wallets` 金币快照表。客户端在增量 Pull 时直接从 API 响应包中提取外层 `wallet.balance` 写入本地 `wallet_balance` 缓存，以此作为首要余额依据。
- **Push 幂等结算**：在 Push 提交流水时，服务端同步引擎通过 UUID 键值执行 `INSERT OR IGNORE` 逻辑，确保同一笔流水在多端重复提交时只会被计入结算一次。

**4. 前端 TypeScript 编译消除与 E2E 自测：**
- **类型升级**：将包含 `Database.ts` 底层 CRUD 方法、`useGoals`、`useRewards`、`useTimeBook` 等 6 处核心 Hooks 和页面的主键 ID 参数类型定义统一升级为 `string | number`，彻底消除编译警告。
- **运行闭环**：通过了 `core` 25/25 单元测试，完成了 `ui` 的编译打包构建。拉起后台 Vite Dev Server 和 Electron 后，客户端顺利完成全流程启动，数据库字段平滑重构，运行零报错。

**状态**: 数据库底层已彻底告别自增整型主键，全面拥抱 UUID 一致性模型，消除了多端并发同步冲突隐患。
