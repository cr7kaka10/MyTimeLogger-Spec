# MyTimeLogger-Spec 项目配置
# 路径：GEMINI.md（项目根目录）
# 继承 ~/.gemini/GEMINI.md 全局规范

---

## 🔁 断点恢复协议（启动时必须执行）

每次新对话开始，第一步读 `openspec/HANDOFF.md`：

```
IF 【活跃变更】有内容：
  → 读对应 proposal.md + tasks.md
  → 按【工作流断点】的"下一步行动"继续
  → 向老板确认恢复点后再动手

IF 【活跃变更】为空：
  → 全新开始，走正常 OpenSpec 流程
```

---

## 项目背景

MyTimeLogger-Spec，时间记录应用，未来扩展 Android 端。

**团队：**
| 姓名 | 职位 |
|------|------|
| 瓜迪奥拉 | 技术总监 |
| C罗 | 全栈开发工程师 |
| 梅西 | 测试工程师兼质量合规官 |
| 司马迁 | 文档记录官 |

详见 `.agent/agents.md`

---

## OpenSpec 文件职责

| 路径 | 职责 | 维护者 |
|------|------|--------|
| `openspec/HANDOFF.md` | 平台切换状态快照 | 司马迁 |
| `openspec/INDEX.md` | 导航首页 | 司马迁 |
| `openspec/MASTER.md` | 全局变更汇总 | 司马迁 |
| `openspec/CONSULT.md` | 技术咨询记录 | 司马迁 |
| `openspec/AGENT-COMM.md` | Agent 通信记录 | 司马迁 |
| `openspec/INTERVIEW.md` | 项目面试指南 | 司马迁 |
| `openspec/PROJECT-MAP.md` | 代码地图 | 司马迁 |
| `openspec/QUESTIONS.md` | 老板提问记录 | 司马迁 |

---

## 本项目补充规则

- 所有时间戳使用北京时间（UTC+8）
- 变更命名：`chg-YYYYMMDD-NNN-名称`
- Task 只有 `[ ]` 和 `[x]` 两种状态
- openspec/ 下跨文件引用使用 Obsidian wiki 链接
- 代码注释用中文
- commit 格式：`[feat/fix/refactor] 简述（chg-YYYYMMDD-NNN）`
- test_runtime/ 加入 .gitignore
