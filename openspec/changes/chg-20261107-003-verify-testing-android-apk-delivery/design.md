## Context

`deploy-test.bat` 的 [1] 顺序为服务端→桌面→Android；桌面 `electron-builder` 停滞时 Android 阶段不会开始。Android 脚本已从当前工作树构建并复制 APK，但固定目标路径可能留下旧包；当前桌面和 Android 版本仍分别为 1.0.0/1.0。

## Goals / Non-Goals

**Goals:** 每次测试部署明确从当前本地工作树重新构建，失败时不得把旧包报成新包；Android 阶段不受桌面打包阻塞；两个客户端显示 2.0 版。

**Non-Goals:** 自动 Git 拉取、手机安装、Electron 打包性能修复、转盘功能改动。

## Decisions

- [1] 保持服务端先行，将 Android 阶段移到桌面阶段之前。[4] 继续只构建 Android。部署前记录 `git rev-parse HEAD`、工作树变更标记和北京时间；这表示本地当前源码，未提交改动也属于本次构建输入。
- Android 构建前清除其固定目标 APK，构建成功后核对文件确实由本次构建生成并输出 SHA256；失败不保留会被误认为新产物的旧包。桌面包同理在日志中核对本次输出及版本。
- 桌面 `package.json` 与锁文件根版本同步为 `2.0.0`；Android `versionName=2.0`、`versionCode=2`。只调整应用展示/安装版本，不调整协议或数据格式版本。
- 保持“APK 已构建、手机安装状态未核验”的准确措辞；部署流程不执行 ADB 安装。

## Risks / Trade-offs

- 桌面打包仍可能停滞，但在此之前 APK 已完成；整套部署仍需如实报告桌面阶段未完成。
- 不自动拉取远端，若用户需要远端最新提交，应先更新本地分支；当前本地 `dev` 比 `origin/dev` 超前，直接拉取不是确定的“最新”定义。
- Android `versionCode` 递增允许从当前 code 1 覆盖升级；签名不同的旧安装仍需按 Android 规则处理。

## Migration Plan

批准后改脚本与两个版本文件，仅做部署入口、版本及本次产物时间/哈希的定向核对；不做额外设备矩阵测试。回退提交即可恢复。

## Open Questions

无。
