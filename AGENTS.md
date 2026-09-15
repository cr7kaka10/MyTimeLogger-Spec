# MyTimeLogger-Spec · Codex / Cursor 配置
# 路径：AGENTS.md（项目根目录）

---

## 🚨 第零法则（最高优先级）

任何实现类请求必须先走 OpenSpec 流程，待老板批准后才能动代码：
1. 瓜迪奥拉输出请求分类
2. 生成 Propose（根因+范围+Task拆解，单条≤3文件/50行）
3. ⛔ 等老板「OK / 确认 / 执行 / 好 / 开始」
4. 老板批准后 C罗 才动手

C罗 直接动代码 → 梅西叫停回滚，从 Propose 重来。
「只是小改动」不构成绕过理由。

---

## 🕐 时区
所有时间戳使用北京时间（UTC+8）。

## 🖥️ Windows PowerShell
禁止 Linux 命令，失败禁止重试。
`ls`→`Get-ChildItem` | `grep`→`Select-String` | `rm -rf`→`Remove-Item -Recurse -Force`

## 🛡️ 禁止 kill IDE 进程
kiro / electron / node（IDE子进程）/ cursor — 这些进程绝对不能 kill。
进程清理必须明确指定目标（如 MyTimeLogger），禁止宽泛扫描。

## 🔍 CodeGraph 优先
有 CodeGraph MCP 时，禁止 grep/glob 扫整个目录。
用 `codegraph_explore` / `codegraph_symbol` / `codegraph_callers` 替代。

## 🔁 断点恢复
每次对话先读 `openspec/HANDOFF.md`，有未完成变更则恢复断点再继续。

## 关键文件
```
openspec/HANDOFF.md      ← 启动必读
openspec/PROJECT-MAP.md  ← 任务前必读
.agent/core.md           ← 永远加载
.agent/roles/            ← 按角色加载
.agent/tasks/            ← 按任务类型加载
```

---
⚠️ 再次确认：没有老板「OK」= 不动代码。
