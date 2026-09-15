# codex.md — Codex 项目配置补充
# 路径：项目根目录/codex.md

## 平台标识
当前平台：Codex CLI（OpenAI）
单实例模拟4人团队，发言时标注角色名。

## 模型分配

| 角色 | 模型 |
|------|------|
| 瓜迪奥拉（技术总监） | GPT-5.5 |
| C罗（全栈开发） | GPT-5.5 |
| 梅西（测试合规） | GPT-5.4-Mini |
| 司马迁（文档） | GPT-5.4-Mini |

推理档位建议：瓜迪奥拉和 C罗 用「高」，其余用「中」。

## 与 Antigravity 无缝衔接
切换前：司马迁更新 HANDOFF.md → AGENT-COMM.md 追加切换记录
切换后：新平台先读 HANDOFF.md，向老板确认恢复点再动手
