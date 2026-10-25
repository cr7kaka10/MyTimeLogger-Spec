## 1. 修正预检误报并补回归场景

- [x] 1.1 在 `deploy/security-preflight.ps1` 中仅豁免 `openspec/` 路径的 tracked-but-ignored 命中，并在 `tests/unit/test_security_hardening.py` 覆盖 OpenSpec 路径放行和其它路径继续拦截；限 2 个文件、≤50 行。DoD：临时 Git 仓库中，强制跟踪的被忽略 OpenSpec 文件不触发该规则；强制跟踪的被忽略普通文件仍输出 `rule=tracked-but-ignored` 并失败。

## 2. 验证部署门禁

- [x] 2.1 运行对应 security hardening pytest，并对当前工作区执行 testing 安全预检；限只读验证、0 个代码文件。DoD：pytest 新旧相关场景通过，且当前仓库预检不再因 `openspec/` 报错；其它安全规则仍能按回归场景拒绝违规输入。
