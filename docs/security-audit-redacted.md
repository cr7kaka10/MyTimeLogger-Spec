# 脱敏安全审计与治理清单（011）

- 审计时间：2026-07-12（北京时间，UTC+8）
- 范围：实施前 `HEAD`、`origin/dev`、`origin/dev..HEAD`，以及本地 ahead 改写后复扫；结果只含路径、规则、提交 ID 和凭据类别。
- 规则：`credential`、`personal-account`、`external-endpoint`、`local-absolute-path`、`personal-temporary-content`；未记录匹配值或正文。

## 命中

| 范围/提交 | 路径 | 规则/类别 | 结论 |
|---|---|---|---|
| `origin/dev` / `53557330448932134d72686808ec9c5334e87d3b` | `server/skills/time-management/config.json` | credential、personal-account、external-endpoint、local-absolute-path | 已推送 P0 |
| `origin/dev` 历史 / `fd063376afd8e96275298daec8603477b4985156` | `server/reports/`（1 个个人报告，文件名脱敏） | personal-temporary-content | 已推送 P0 |
| `origin/dev` 历史 / `a117146417cdafc9abbd2e68acf7be8205b484b7` | `start-all.bat` | personal-account、external-endpoint | 已推送 P0 |
| 原 `HEAD` / 恢复引用 `30061fb5de388a548298bdf13ac4fa570f51c73b` | `server/skills/time-management/config.json` | 同上 | 安全恢复引用可达 |
| 原 `HEAD` / 恢复引用 `30061fb5de388a548298bdf13ac4fa570f51c73b` | `start-all.bat` | personal-account | 安全恢复引用可达 |
| 原 `HEAD` / 恢复引用 `30061fb5de388a548298bdf13ac4fa570f51c73b` | `server/reports/`（1 个个人报告，文件名脱敏） | personal-temporary-content | 安全恢复引用可达 |
| 原 `origin/dev..HEAD` / `1198f73151565ed1df12d8acdfd0ce7fd950168e` | `assets/tmp/`（2 个文件，文件名脱敏） | personal-temporary-content | 已从 `dev` ahead 剔除，仅恢复引用可达 |

- 首次规则命中：技能配置 `3573a9a4fbe08ecf53e34c570506a0b48e00040d`；启动脚本 `a117146417cdafc9abbd2e68acf7be8205b484b7`。
- 实施后复扫：`git rev-list --objects origin/dev..dev` 中 `assets/tmp/` 命中为 0；`origin/dev` 未改写、未 push。
- 新增删除提交不能清除已推送 blob；P0 在凭据失效并完成历史决策前持续阻断公开 push。

## 凭据轮换与历史治理

| Provider/字段类别 | 责任方 | 动作 | 验证 |
|---|---|---|---|
| aTimeLogger：账号、密码、外部端点 | 仓库所有者 | 轮换密码/会话并仅写入用户 provider-binding | 旧凭据失败；新绑定状态 configured |
| WeChat：webhook secret URL | 仓库所有者 | 重新签发 webhook，撤销旧地址 | 旧地址拒绝；新绑定状态 configured |
| 启动/部署：个人账号、真实地址、本机路径 | 维护者 | 从当前树和模板移除 | 预检零命中 |
| Git 远端历史 | 仓库管理员 | 选择重写历史或新建无旧历史发布仓库 | 全部远端可达对象复扫零命中 |

- `origin/dev` 历史重写和 force-push 必须再次获得老板单独明确批准；本变更不得执行。
- 协作者迁移、恢复引用和旧凭据失效证明必须在批准后、远端操作前就绪。

## 2026-07-14 所有者凭据复核

- 仅输出字段名的历史复核确认：`origin/dev` 的技能配置只有一版；WeChat 仅有启用开关，未出现非空 webhook URL，当前项目也没有该通知器的外部调用者。
- 所有者确认历史 aTimeLogger 旧认证属性不含泄露的有效密码；因此没有待轮换的活动第三方凭据。个人账号、外部地址和历史个人报告仍须通过 Git 重写移除。

## 2026-07-14 `origin/dev` 重写结果

- 隔离重写后以独立 bare clone 复扫：技能真实配置、`server/reports/`、`assets/tmp/` 的历史提交计数均为 0；安全 `start-all.bat` 仅保留一个版本，未命中个人邮箱或非本地 IP URL。
- `origin/dev` 已从 `5355733` force-push 至 `ab2bd70`。`origin/main`、`gitee/dev`、`gitee/main` 不在本次授权范围，仍需单独决策，不能宣称全部远端历史已清零。

## 2026-07-14 其余获授权远端重写结果

- 老板已授权并完成 `origin/main`、`gitee/dev`、`gitee/main` 的隔离 bare clone 重写与 `--force-with-lease` 推送；最终旧/新 tip 分别为 `2ffa508→ec8d095`、`1f98d87→bc22172`、`2ffa508→af94226`。
- 每条远端均以新的单分支 clone 复扫：技能真实配置、`server/reports/`、`assets/tmp/` 和技能配置内旧认证属性来源提交计数均为 0；安全 `start-all.bat` 历史仅保留一个版本，个人邮箱、非 loopback IP URL 以及 WeChat 代码/配置命中均为 0。
- 扫描仅记录 ref、短 SHA、规则和计数，未输出 blob 正文、秘密值或私有配置。
