# 睡眠分析云端化执行计划 v2.0

## 1. 目标

把当前依赖 PC 端常驻的“手机上传截图 -> AI 解析 -> 睡眠报告 -> 手机查看结果”流程，迁移为可公网访问的云端服务。PC 端只负责启动时和定时拉取云端已完成的数据，并同步到本地 `huawei_sleep_data` 表。

v1 不做全量 MySQL 共享，不同步任务、金币、习惯、专注流水，只同步睡眠分析结果。

## 2. 已落地模块

### 2.1 `sleep_analyzer.py`

纯 Python 睡眠分析核心，无 PyQt 依赖，可被桌面端和云端服务共用。

职责：
- 读取 AI 配置。
- 压缩/预处理睡眠截图。
- 调用视觉模型提取睡眠原始字段。
- 强力提取 JSON。
- 归一化时长和数值字段。
- 校验 `total_sleep_min == deep_sleep_min + light_sleep_min + rem_sleep_min`。
- 执行截图日期校验和年份纠偏。
- 调用 `generate_comprehensive_report()` 生成报告。

### 2.2 `server_sleep_store.py`

云端 Buffer SQLite 存储层，默认数据库为 `server_sleep_jobs.db`。

核心表：

```sql
CREATE TABLE IF NOT EXISTS server_sleep_jobs (
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
);
```

状态：
- `queued`
- `running`
- `done`
- `error`

### 2.3 `server_sleep_api.py`

FastAPI 云端服务入口。

接口：
- `GET /ping`
- `GET /`
- `POST /upload`
- `GET /status/{request_id}`
- `GET /events/{request_id}`
- `GET /sync_data?since=YYYY-MM-DD HH:MM:SS`
- `POST /ack_sync`
- `GET /recent?limit=10`
- `POST /reflection`

安全：
- 除 `/ping` 和 `/` 外，所有接口必须带 `X-Auth-Token`。
- Token 来源：`SLEEP_AUTH_TOKEN` 环境变量。
- 上传限制：仅图片，最大 15MB。
- AI Key 来源环境变量，不写入仓库。

AI 环境变量：
- `VISION_BASE_URL`
- `VISION_API_KEY`
- `VISION_MODEL`
- `TEXT_BASE_URL`
- `TEXT_API_KEY`
- `TEXT_MODEL`
- `BACKUP_BASE_URL`
- `BACKUP_API_KEY`
- `BACKUP_MODEL`
- `SLEEP_AUTH_TOKEN`

### 2.4 `server_sleep_client.py`

PC 端云同步客户端。

配置项：

```json
"server_sleep_sync": {
    "enabled": false,
    "base_url": "",
    "auth_token": "",
    "sync_interval_sec": 300,
    "last_sync_at": ""
}
```

同步规则：
- 使用 `last_sync_at` 拉取云端增量。
- 本地无记录时直接写入。
- 本地有记录时，仅当云端 `updated_at` 更新才覆盖指标和报告。
- 本地 `sleep_reflection` 非空且云端为空时，保留本地评价。
- 成功处理后调用 `/ack_sync`。

## 3. 执行和测试步骤

### 3.0 Docker 一键启动

首次在本机生成 `.env`：

```powershell
python scratch/create_server_env_from_local.py
```

该脚本会：
- 从本地 `config.json` 复制视觉/文本/备用模型配置。
- 从 `skills/time-management/config.json` 复制 aTimeLogger 配置。
- 自动生成随机 `SLEEP_AUTH_TOKEN`。
- 写入 `.env`，该文件已加入 `.gitignore`，不要提交。

启动云端服务：

```powershell
docker compose up -d --build
```

查看状态：

```powershell
docker compose ps
docker compose logs -f sleep-server
```

停止服务：

```powershell
docker compose down
```

如果 PC 端也在同一台机器上连接本地 Docker 服务，可执行：

```powershell
python scratch/enable_local_server_sync.py
```

该脚本会读取 `.env` 的 `SLEEP_AUTH_TOKEN`，并把本地 `config.json` 的 `server_sleep_sync` 指向 `http://127.0.0.1:8000`。

### 3.1 本地核心测试

```bash
python scratch/test_sleep_analyzer_core.py
python scratch/test_server_sleep_store.py
```

### 3.2 启动云端服务

PowerShell 示例：

```powershell
$env:SLEEP_AUTH_TOKEN="change-me-to-a-long-random-token"
$env:VISION_API_KEY="your-vision-key"
$env:VISION_MODEL="glm-4v-flash"
$env:VISION_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
uvicorn server_sleep_api:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/ping
```

上传测试：

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -H "X-Auth-Token: change-me-to-a-long-random-token" \
  -F "file=@attachments/sleep_2026-05-13.jpg"
```

### 3.3 PC 客户端同步

在根目录 `config.json` 中启用：

```json
"server_sleep_sync": {
    "enabled": true,
    "base_url": "https://your-domain.example",
    "auth_token": "change-me-to-a-long-random-token",
    "sync_interval_sec": 300,
    "last_sync_at": ""
}
```

PC 启动后 3 秒执行第一次同步，之后按 `sync_interval_sec` 循环同步。

## 4. 部署建议

推荐：
- Python 3.10+
- `uvicorn server_sleep_api:app --host 127.0.0.1 --port 8000`
- Nginx/Caddy 反代 HTTPS 到本地 8000。
- 使用 systemd、Windows 服务或进程守护工具保证常驻。

生产检查：
- HTTPS 可用。
- `SLEEP_AUTH_TOKEN` 至少 32 字符。
- AI Key 仅放服务器环境变量。
- 日志不打印 token 和 API key。
- `server_attachments/` 定期清理。
- `server_sleep_jobs.db` 定期备份。

## 5. 后续增强

- 云端定期清理：已同步 7 天后的图片、30 天后的 Buffer 记录。
- 手机端页面继续优化，加入更完整的历史报告和评价编辑体验。
- 服务端报告生成可进一步减少对 `skills/time-management/config.json` 的依赖，完全改为环境变量配置。
- 加入 API 频率限制，进一步防止恶意刷模型费用。
