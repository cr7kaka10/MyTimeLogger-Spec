# -*- coding: utf-8 -*-
"""同步功能服务端常量（运行时常量，非用户可编辑配置）"""

# 滴答清单后台轮询间隔（秒，默认 5 分钟，不建议低于 60）
TICKTICK_POLL_INTERVAL_SEC = 300

# SSE 保活心跳间隔（秒）— 对应 server.py event_stream() 的 wait_for timeout
SSE_KEEPALIVE_INTERVAL_SEC = 30

# 版本化 Pull 分页限制
PULL_LIMIT_DEFAULT = 500
PULL_LIMIT_MAX = 1000
