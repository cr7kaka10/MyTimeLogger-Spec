# aTimeLogger Pro API 接口文档 (完整版)

## 概述

本文档描述了 aTimeLogger Pro (https://app.atimelogger.pro) 的所有API接口。

**基础URL**: `https://app.atimelogger.pro`

**认证方式**: JWT Bearer Token

**测试账号**: user@example.com / mufc130130131

---

## 认证接口

### 1. 用户登录

**接口**: `POST /auth/jwt`

**描述**: 用户登录并获取JWT访问令牌

**请求头**:
```
Content-Type: application/json
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Origin: https://app.atimelogger.pro
```

**请求体**:
```json
{
  "username": "your_email@example.com",
  "password": "your_password"
}
```

**响应 (200)**:
```json
{
  "token": "eyJhbGciOiJIUzM4NCJ9...",
  "refreshToken": "eyJhbGciOiJIUzM4NCJ9...",
  "deviceId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

**使用方式**: 登录后在请求头中添加Authorization:
```
Authorization: Bearer <token>
```

---

## 可用API接口 (共10个)

### 2. 获取时间间隔数据 (核心API) ⭐⭐⭐

**接口**: `POST /api/intervals`

**描述**: 获取指定日期范围内的时间记录数据

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体**:
```json
{
  "from": "2026-03-01",
  "to": "2026-03-13"
}
```

**可选查询参数**:
| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| groupBy | string | 分组方式 (DAY/WEEK/MONTH) | 无 |
| page | int | 页码 | 0 |
| size | int | 每页数量 | 20 |

**响应 (200)**:
```json
{
  "content": [
    {
      "title": "Today",
      "intervals": [
        {
          "id": "019ce30d-778c-7a14-b80e-5ae6c75fc172",
          "start": "2026-03-12T16:19:24.000Z",
          "finish": "2026-03-12T17:17:16.000Z",
          "from": 1773332364,
          "to": 1773335836,
          "typeId": "442c6aa2-7054-46e6-8240-5f79be342372",
          "activityId": "019ce2d8-7d7e-745b-bc84-18ca5a611c44",
          "tags": [],
          "comment": null,
          "duration": 3472
        }
      ]
    }
  ]
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 记录ID |
| start | string | 开始时间 (ISO 8601) |
| finish | string | 结束时间 (ISO 8601) |
| from | integer | 开始时间戳 |
| to | integer | 结束时间戳 |
| typeId | string | 活动类型ID |
| activityId | string | 活动ID |
| tags | array | 标签列表 |
| comment | string/null | 备注 |
| duration | integer | 持续时间 (秒) |

---

### 3. 获取统计数据 ⭐⭐

**接口**: `POST /api/statistics`

**描述**: 获取指定日期范围内的统计数据，支持按天/周/月分组

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体**:
```json
{
  "from": "2026-03-01",
  "to": "2026-03-13",
  "groupBy": "DAY"
}
```

**groupBy可选值**:
| 值 | 说明 |
|------|------|
| DAY | 按天分组 |
| WEEK | 按周分组 |
| MONTH | 按月分组 |

**响应 (200)**:
```json
{
  "periods": [
    {
      "title": "Mar 1",
      "info": {
        "total": 82125
      },
      "statistics": [
        {
          "types": ["061b1180-c94f-4bcb-931e-87322fbc007e"],
          "duration": 38955,
          "children": []
        }
      ],
      "groupedStatistics": [...]
    }
  ],
  "total": {
    "title": "Total",
    "info": {
      "total": 2369012
    },
    "statistics": [...],
    "groupedStatistics": [...]
  },
  "types": [
    {
      "id": "061b1180-c94f-4bcb-931e-87322fbc007e",
      "name": "工作",
      ...
    }
  ]
}
```

---

### 4. 获取用户信息

**接口**: `GET /api/users/me`

**请求头**:
```
Authorization: Bearer <token>
Accept: application/json
```

**响应 (200)**:
```json
{
  "username": "user@example.com",
  "firstName": "cr",
  "lastName": "kaka",
  "timeZone": null,
  "language": null,
  "plan": "premium-plus",
  "expires": "2022-12-31",
  "permissions": [],
  "settings": {
    "actionOnStart": "STOP",
    "fullPath": true
  }
}
```

---

### 5. 获取时区列表

**接口**: `GET /api/users/timezones`

**响应 (200)**:
```json
["Africa/Abidjan", "Africa/Accra", ...]
```

---

### 6. 获取活动类型列表

**接口**: `GET /api/types`

**响应 (200)**:
```json
[
  {
    "id": "75f9c4c0-a68f-41f0-8d56-ceed37a47c7d",
    "name": "输入",
    "group": false,
    "color": 16733522,
    "imageId": "cat_96",
    "parentId": null,
    "order": 1,
    "deleted": false,
    "archived": false,
    "occurrence": false
  }
]
```

---

### 7. 获取当前活动

**接口**: `GET /api/activities`

**响应 (200)**:
```json
{
  "activities": [
    {
      "id": "019ce30d-7798-790a-a0ba-4917ff96826d",
      "typeId": "061b1180-c94f-4bcb-931e-87322fbc007e",
      "intervals": [],
      "status": "RUNNING",
      "start": "2026-03-12T17:17:16.000Z",
      "comment": null,
      "tags": [],
      "duration": 0
    }
  ],
  "types": [...]
}
```

**状态说明**:
| 状态 | 说明 |
|------|------|
| RUNNING | 正在运行 |
| PAUSED | 已暂停 |
| STOPPED | 已停止 |

---

### 8. 获取特定活动详情

**接口**: `GET /api/activities/{id}`

**响应 (200)**:
```json
{
  "id": "019ce30d-7798-790a-a0ba-4917ff96826d",
  "typeId": "061b1180-c94f-4bcb-931e-87322fbc007e",
  "status": "RUNNING",
  "start": "2026-03-12T17:17:16.000Z",
  "comment": null,
  "tags": [],
  "duration": 0
}
```

---

### 9. 获取标签列表

**接口**: `GET /api/tags`

**响应 (200)**:
```json
{
  "content": ["B站", "主动中断", "出游", "学习方法", "家务"],
  "pageable": {...},
  "totalPages": 3,
  "totalElements": 15
}
```

---

### 10. 获取过滤器列表

**接口**: `GET /api/filters`

**响应 (200)**:
```json
[
  {
    "id": "24553dc8-3911-4c07-93a8-d3a5984c3484",
    "name": "昨天报告(睡眠除外)",
    "types": ["cb5373fc-235a-4704-83b1-078e1522e6ec", ...],
    ...
  }
]
```

---

## 不可用API (服务端问题)

以下API返回500错误，错误信息为 `"Error: ask developer for details"`，需要联系aTimeLogger开发者修复：

| 接口 | 方法 | 说明 | 错误信息 |
|------|------|------|----------|
| `/api/records` | GET/POST | 时间记录 | 500 Internal Server Error |
| `/api/timelogs` | GET/POST | 时间日志 | 500 Internal Server Error |
| `/api/time-entries` | GET/POST | 时间条目 | 500 Internal Server Error |
| `/api/export` | POST | 数据导出 | 500 Internal Server Error |
| `/api/reports` | GET/POST | 报告 | 500 Internal Server Error |
| `/api/summary` | GET/POST | 摘要 | 500 Internal Server Error |
| `/api/dashboard` | GET/POST | 仪表板 | 500 Internal Server Error |
| `/api/settings` | GET | 设置 | 500 Internal Server Error |
| `/api/settings/user` | GET | 用户设置 | 500 Internal Server Error |
| `/api/categories` | GET | 分类 | 500 Internal Server Error |
| `/api/projects` | GET | 项目 | 500 Internal Server Error |
| `/api/activities/start/` | POST | 开始活动 | 500 Internal Server Error |
| `/api/activities/stop/` | POST | 停止活动 | 500 Internal Server Error |
| `/api/activities/pause/` | POST | 暂停活动 | 500 Internal Server Error |
| `/api/activities/resume/` | POST | 恢复活动 | 500 Internal Server Error |

**注意**: 这些API返回的错误信息为 `"Error: ask developer for details"`，说明是服务端实现问题，需要联系aTimeLogger开发者解决。

---

## Python完整调用示例

```python
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "https://app.atimelogger.pro"

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Origin': 'https://app.atimelogger.pro'
})

# 1. 登录
login_data = {
    "username": "your_email@example.com",
    "password": "your_password"
}
resp = session.post(f"{BASE_URL}/auth/jwt", json=login_data)
token = resp.json()['token']

# 2. 设置认证头
session.headers['Authorization'] = f'Bearer {token}'

# 3. 获取时间间隔数据 (核心功能)
payload = {
    "from": "2026-03-01",
    "to": "2026-03-13"
}
resp = session.post(f"{BASE_URL}/api/intervals", json=payload)
intervals_data = resp.json()

# 4. 获取统计数据 (按天分组)
stats_payload = {
    "from": "2026-03-01",
    "to": "2026-03-13",
    "groupBy": "DAY"
}
resp = session.post(f"{BASE_URL}/api/statistics", json=stats_payload)
stats_data = resp.json()

# 5. 获取用户信息
resp = session.get(f"{BASE_URL}/api/users/me")
user_info = resp.json()

# 6. 获取活动类型
resp = session.get(f"{BASE_URL}/api/types")
types = resp.json()

# 7. 获取当前活动
resp = session.get(f"{BASE_URL}/api/activities")
activities = resp.json()

# 8. 获取标签
resp = session.get(f"{BASE_URL}/api/tags")
tags = resp.json()

# 9. 获取过滤器
resp = session.get(f"{BASE_URL}/api/filters")
filters = resp.json()

# 10. 获取时区
resp = session.get(f"{BASE_URL}/api/users/timezones")
timezones = resp.json()

print(f"获取到 {len(intervals_data['content'])} 天的数据")
print(f"统计: {len(stats_data['periods'])} 个时间段")
```

---

## 数据提取结果

成功提取的数据:
- ✓ 用户信息
- ✓ 活动类型 (15个)
- ✓ 标签列表 (15个)
- ✓ 时间记录 (84条/5天)
- ✓ 统计数据 (按天/周/月)
- ✓ 当前活动
- ✓ 过滤器
- ✓ 时区列表

---

## 调试记录

**调试日期**: 2026-03-14

**测试的所有API端点**: 40+

**可用的API**: 10个

**调试方法**:
1. 分析前端JavaScript代码 (main.js)
2. 测试GET/POST各种组合
3. 尝试不同的请求参数格式
4. 检查500错误的具体响应

**结论**: 部分API返回 `"Error: ask developer for details"` 错误，需要联系aTimeLogger开发者修复。

---

**文档版本**: v2.0
**最后更新**: 2026-03-14
