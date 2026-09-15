"""旧导入路径兼容层；新代码统一使用 statistics_start_date。"""

try:
    from .statistics_start_date import (
        DEFAULT_STATISTICS_START_DATE,
        StatisticsStartDate,
        resolve_statistics_start_date,
    )
except ImportError:  # 兼容从 server 目录直接启动的旧入口。
    from statistics_start_date import (
        DEFAULT_STATISTICS_START_DATE,
        StatisticsStartDate,
        resolve_statistics_start_date,
    )


DEFAULT_CHECKLIST_SYNC_START_DATE = DEFAULT_STATISTICS_START_DATE
ChecklistSyncStartDate = StatisticsStartDate
resolve_checklist_sync_start_date = resolve_statistics_start_date
