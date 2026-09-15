# 文档维护指南

本指南说明如何维护 MyTimeLogger 项目的 OpenSpec 文档体系。

## 文档结构

```
openspec/
├── changes/                          # 进行中的变更
│   └── document-system-baseline/    # 系统基线文档（当前 Change）
│       ├── .openspec.yaml            # Change 元数据
│       ├── proposal.md               # 变更提案
│       ├── design.md                 # 设计决策
│       ├── tasks.md                  # 任务清单
│       └── specs/                    # Capability 规范文件
│           ├── pc-client-architecture/
│           ├── server-architecture/
│           ├── data-model/
│           ├── sleep-analysis-workflow/
│           ├── sync-mechanism/
│           └── deployment/
└── archive/                          # 已归档的历史变更
```

## 何时更新文档

| 触发条件 | 需要更新的文档 |
| :--- | :--- |
| 新增功能模块 | 在对应 Capability spec 中添加新 Scenario |
| 修改现有功能 | 在对应 Scenario 前加 `MODIFIED:` 标记，说明变更内容 |
| 删除功能 | 在对应 Scenario 前加 `REMOVED:` 标记 |
| 新增 API 端点 | 更新 `server-architecture` spec |
| 修改数据库 Schema | 更新 `data-model` spec，同步更新 `schema.py` 注释 |
| 新增配置项 | 更新 `deployment` spec 的环境变量章节 |
| 发现新技术债 | 在 `design.md` 的技术债汇总章节追加记录 |

## 如何新增一个 Change

当需要开发新功能时，创建新的 Change 目录：

```bash
# 1. 创建 Change 目录
mkdir openspec/changes/<change-name>

# 2. 创建必要文件
touch openspec/changes/<change-name>/proposal.md
touch openspec/changes/<change-name>/design.md
touch openspec/changes/<change-name>/tasks.md
touch openspec/changes/<change-name>/.openspec.yaml
mkdir openspec/changes/<change-name>/specs
```

`.openspec.yaml` 格式示例：

```yaml
change: <change-name>
status: in_progress   # in_progress | completed
created_at: "2026-05-17"
description: "简短描述这个 Change 的目标"
```

## Scenario 格式规范

所有 spec 文件中的需求场景必须使用以下格式：

```markdown
#### Scenario: <场景名称>
- **WHEN** <触发条件>
- **THEN** <预期结果>
- **AND** <附加结果（可选）>
```

**示例：**

```markdown
#### Scenario: 状态转换
- **WHEN** 学习时长达到长休息阈值（90 分钟）
- **THEN** 状态从 `studying` 转换到 `long_breaking`
- **AND** 播放胜利音效
- **AND** 弹出专注总结对话框
```

## 技术债记录规范

在 `design.md` 的技术债章节，使用以下格式记录：

```markdown
| TD-XXX | 问题描述 | 所在文件 | 优先级 |
```

优先级定义：
- **P0**：影响功能可用性，需立即修复
- **P1**：影响稳定性或安全性，计划修复
- **P2**：代码质量问题，技术改进迭代中处理

## 归档已完成的 Change

当一个 Change 的所有任务完成后，将其归档：

```bash
# 将 Change 从 changes/ 移动到 archive/
mv openspec/changes/<change-name> openspec/archive/<change-name>

# 更新 .openspec.yaml 状态
# status: completed
# completed_at: "YYYY-MM-DD"
```

## 文档与代码一致性检查

定期（建议每月一次）执行以下检查：

1. **Schema 一致性**：对比 `data-model` spec 与 `app/models/schema.py` 中的表结构
2. **API 一致性**：对比 `server-architecture` spec 与 `server/server.py` 中的端点定义
3. **状态机一致性**：对比 `pc-client-architecture` spec 与 `app/core/logic.py` 中的状态转换
4. **配置一致性**：对比 `deployment` spec 与 `config/config.json` 中的配置项

## 常见问题

**Q: 文档和代码不一致怎么办？**

以代码为准，更新文档。文档描述的是"应该是什么"，代码是"实际是什么"。如果两者差异较大，说明需要创建新的 Change 来对齐。

**Q: 一个功能跨多个 Capability，应该放在哪里？**

放在最相关的 Capability 中，并在其他相关 Capability 中添加交叉引用。例如，TickTick 任务同步的奖励发放逻辑，主要放在 `sync-mechanism`，在 `pc-client-architecture` 中添加引用说明。

**Q: 如何处理实验性功能？**

在 Scenario 前加 `[EXPERIMENTAL]` 标记，说明该功能尚不稳定，可能在未来版本中变更或移除。
