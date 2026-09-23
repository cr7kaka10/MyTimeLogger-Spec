"""仅运维文件可登记已验证能力；用户同步配置不能打开硬删除。"""
import json
import os
from pathlib import Path
try:
    from .habit_lifecycle_contract import HabitLifecycleContract
except ImportError:
    from habit_lifecycle_contract import HabitLifecycleContract


def load_habit_contract(host):
    path = os.getenv('MTL_HABIT_LIFECYCLE_CONTRACT_FILE')
    if not path:
        return HabitLifecycleContract(host)
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    record = data.get(host.lower(), {})
    status = record.get('archived_status')
    if status is not None and (type(status) is not int or status == 0):
        raise ValueError('invalid_habit_lifecycle_contract')
    return HabitLifecycleContract(host, status,
        record.get('archived_detail_readable') is True, record.get('deleted_detail_is_404') is True,
        str(record.get('evidence_ref') or ''), record.get('hard_delete_enabled') is True,
        record.get('compatible_clients_verified') is True, record.get('backup_restore_verified') is True)
