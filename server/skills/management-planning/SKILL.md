# MyTimeLogger 管理方案 Skill

版本：`management-planning-skill-v2`
规则版本：`management-planning-v3`

本 skill 是服务端管理方案 review、proposal、patch 的固定任务流程。模型只接收服务端构造的最小事实快照，不连接 SQLite、不执行 SQL、不读取文件，也不能提供或覆盖 `evidence`。首页 AI 输入框、未来 CLI 和导入/微调流程必须复用同一服务端合同。

禁止在输出中提供或覆盖 `evidence`；该字段只能由服务端根据当前账号数据库附加。

## 一、数据库边界与读取字典

### 1. 唯一数据库和账号边界

- 唯一事实库是服务端当前运行配置打开的用户业务 SQLite，schema 定义位于 `server/models/server_schema.py`。
- 每条查询必须使用当前认证账号的 `user_id` 参数过滤；禁止使用模型、请求体或 logical_key 提供的 user_id。
- 模型只收到 `ManagementPlanService` 生成的白名单快照；模型、客户端和 CLI 不得访问 SQLite 路径、连接对象或 SQL。
- 所有时间以北京时间（UTC+8）解释；自然语言回复必须使用简体中文。

### 2. 允许读取的表、字段和关联

| 领域 | 表和允许字段 | 关联与过滤 | 用途 |
| --- | --- | --- | --- |
| 任务/习惯奖励 | `server_reward_config(item_type,item_id,coins,penalty,updated_at)` | `user_id=:current_user_id`；`item_type` 仅 `task`/`habit` | 完成金币、失败惩罚 |
| 任务事实 | `server_tasks(id,title,priority,status,category_id,due_date,tags,updated_at)` | `user_id=:current_user_id` | 滴答任务标题、优先级、状态、截止日 |
| 习惯事实 | `server_habits(id,name,difficulty,repeat_rule,category_id,is_active,updated_at)` | `user_id=:current_user_id` | 习惯名称、频率和启用状态 |
| 学习目标 | `server_learning_objectives(id,title,status,duration,baseline,target_description,updated_at)` | `user_id=:current_user_id` | Objective 基础和状态 |
| 学习关键结果 | `server_learning_krs(id,objective_id,title,target_value,current_value,updated_at)` | `user_id=:current_user_id`；`objective_id` 必须属于当前账号的 Objective | KR 目标值和当前进度 |
| 学习任务 | `server_learning_tasks(id,kr_id,title,status,category_id,priority,reward,due_date,updated_at)` | `user_id=:current_user_id`；`kr_id` 必须属于当前账号的 KR | 可执行学习任务和金币奖励 |
| 目标 | `server_goals(id,title,category_id,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,updated_at)` | `user_id=:current_user_id` | 周期目标、奖惩、激活状态 |
| 目标分类绑定 | `server_goal_category_bindings(goal_id,category_id,updated_at)` | `user_id=:current_user_id`；按 `goal_id` 连接目标 | 一个目标绑定多个时间分类 |
| 时间分类 | `server_categories(id,name,color)` | `user_id=:current_user_id` | 解释目标/任务的时间来源 |
| 运动版本 | `server_exercise_plan_versions(version,title,source_name,is_active,exercise_points,updated_at)` | `user_id=:current_user_id`；只取活动版本及其版本标识 | 当前运动计划和积分事实 |
| 运动项目 | `server_exercise_plan_items(id,plan_version,day_key,variant,section,sort_order,name,sets,intensity,progression,is_active,updated_at)` | `user_id=:current_user_id`；`plan_version` 必须属于当前账号 | 运动动作、日程日和强度 |
| 运动日程 | `server_exercise_plan_schedule_items(id,plan_version,schedule_type,sort_order,time,item,note,accent,updated_at)` | `user_id=:current_user_id`；`plan_version` 必须属于当前账号 | 运动时间安排 |
| 商品奖励 | `server_rewards(id,title,price,description,unlock_source_type,unlock_source_id,inventory_mode,inventory_limit,unlock_required_count,is_active,updated_at)` | `user_id=:current_user_id`；解锁来源按 `(unlock_source_type,unlock_source_id)` 关联 | 价格、库存、解锁条件 |

来源类型只能使用 `checklist_task`、`habit`、`learning_task`、`exercise_checkin`、`goal`。如果来源记录不存在，必须显示“来源已不存在”，不得根据标题猜测来源。

### 3. 硬性排除

不得读取、传递或生成：`server_reward_ledger`、`server_backpack_events`、钱包快照、余额、原始 TickTick JSON、S3/TickTick/大模型配置、Token、密码、日记、截图、SQL、URL、小时级日历和睡眠实测明细。睡眠只能作为已提供摘要中的约束；不得创建、修改或伪造睡眠记录。

## 二、固定任务流程

### Review（总结/盘点/分析当前）

1. 先读取 `review_evidence.reward_rules` 和 `review_evidence.store_items`，逐项核对具体名称、金币、价格、库存和解锁次数。
2. 输出当前基础、风险、建议；结论必须引用上下文中已有名称和数值，缺失时明确写“未知”。
3. 固定输出 `items: []`，不能创建草案项目；review 只读，不能校验或应用。

合同：

```json
{"mode":"review","policy_version":"management-planning-v3","summary":"简体中文总结","review":{"strengths":["简体中文"],"risks":["简体中文"],"recommendations":["简体中文"]},"items":[]}
```

### Proposal（生成/调整可执行方案）

1. 优先复用当前正式方案和绑定，避免重复创建。
2. 至少返回一个项目；每项必须有 ASCII `namespace.key`、合法 `type` 和 `action`。
3. `action` 仅允许 `create`、`update`、`bind`、`keep`、`disable`；奖励必须服从事实快照中的金币和商品价格边界。
4. 不确定时生成可审阅建议，不编造余额、流水、价格或来源。

合同：

```json
{"mode":"proposal","policy_version":"management-planning-v3","title":"简体中文方案名","plan_key":"self-management","summary":"简体中文摘要","items":[{"logical_key":"habit.morning-brush","type":"local_habit","action":"create","title":"早起刷牙","reason":"简体中文理由"}]}
```

### Patch（微调已发布版本）

Patch 只描述既有 logical_key 的最小差异，使用 `add`、`update`、`disable`、`keep`；必须引用父 revision，不能直接改历史版本。

合同：

```json
{"patch_version":"1","parent_revision_id":"服务端提供的版本ID","items":[{"logical_key":"reward.weekend-game","action":"update","value":{"price":20},"reason":"简体中文理由"}]}
```

## 三、从生成到生效

1. 服务端根据请求判定 `review` 或 `proposal`，读取当前账号快照并调用文本大模型。
2. 服务端校验 JSON、字段、logical_key、动作、奖励边界和简体中文；不合格模型结果最多重试一次。
3. 合格 proposal 保存为 `draft`，携带 `policy_version`、`skill_version`、`context_version`；生成阶段不得写入任务、习惯、学习、运动、目标、商品或奖励定义。
4. 用户点击“校验变更”后，服务端重新读取当前账号事实并比较 `context_version`/evidence digest，返回影响、冲突或过期原因。
5. 只有最新预检成功，用户明确点击“确认并应用”，服务端才在同账号事务中调用领域命令并发布新 revision；失败则全部回滚。
6. 变更文档记录父版本、动作、稳定记录 ID、预检摘要、版本号、语言校验和操作者来源；历史入口只展示已发布 revision。

禁止把“生成草案”当成“已经生效”。review 永远不能应用；过期或冲突草案必须重新校验或重新生成。

## 四、简体中文输出规则

`title`、`summary`、`reason`、`description`、`name` 以及 review 三组数组的每一项都必须使用简体中文。必要的英文品牌、课程名或技术名词可以出现在中文句子中；logical_key、枚举、ID、时间和数值不参与语言检测。首次不合格时只允许一次中文重试，仍不合格返回 `management_plan_non_simplified_chinese`，不得保存草案或应用。

## 五、禁止的应用行为

不得自动确认、自动扣币、自动消费、自动结算、自动完成任务或直接执行模型文本中的 SQL。所有业务写入必须由服务端现有领域命令完成，客户端和未来 CLI 只能调用服务端 API。
