# 远端历史治理决策（011）

- 决策时间：2026-07-14（北京时间）
- 已选策略：重写并 force-push `origin/dev`；不创建新的无旧历史发布仓库。
- 凭据复核：所有者确认历史 aTimeLogger 密码字段不是泄露的有效密码；历史 WeChat 配置未含非空 webhook URL，且通知模块无外部调用者。
- 协作者影响：冻结对 `origin/dev` 的推送；改写后协作者必须重新 clone，或在确认无本地工作后将本地 `dev` 重置到新的 `origin/dev`。
- 恢复方案：执行前记录远端旧 tip，并建立仅本机可见的恢复引用；该引用绝不推送。
- 范围限制：本次授权仅覆盖 `origin/dev`。审计显示 `origin/main`、`gitee/dev`、`gitee/main` 仍有 P0 路径，未经单独授权不改写它们，也不得宣称全部远端历史已清零。
- 执行结果：2026-07-14 已在隔离镜像以 `git filter-repo` 重写并独立复扫，再以 `--force-with-lease` 将 `origin/dev` 从 `5355733` 推送到 `ab2bd70`。

## 2026-07-14 补充授权执行结果

- 老板后续授权重写并 force-push `origin/main`、`gitee/dev`、`gitee/main`；三条 ref 均在独立 bare clone 中过滤，当前工作树和本地恢复 refs 从未推送。
- 远端更新：`origin/main` `2ffa508→ec8d095`，`gitee/dev` `1f98d87→bc22172`，`gitee/main` `2ffa508→af94226`。
- 协作者必须重新 clone；如确认没有本地工作，也可执行 `git fetch --all --prune` 后将对应本地分支显式 reset 到远端。不得把重写前的本地提交直接推回这些分支。
- 本地 Git force-push 无法立即删除 GitHub/Gitee 的 fork、缓存、PR refs、搜索索引或其他人已下载的旧 clone；这些范围须由仓库管理员按托管平台能力另行处理。
