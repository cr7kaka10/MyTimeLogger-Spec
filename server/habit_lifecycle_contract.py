"""能力必须来自已校准 host 证据；线上默认不启用归档/404 删除映射。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class HabitLifecycleContract:
    host: str
    archived_status: int | None = None
    archived_detail_readable: bool = False
    deleted_detail_is_404: bool = False
    evidence_ref: str = ''
    hard_delete_enabled: bool = False
    compatible_clients_verified: bool = False
    backup_restore_verified: bool = False

    def state(self, record):
        status = record.get('status')
        if type(status) is not int:
            return 'unknown'
        if status == 0:
            return 'active'  # 只读基线已确认当前列表中活动样本为 0。
        if self.evidence_ref and self.archived_status is not None and status == self.archived_status:
            return 'archived'
        return 'unknown'

    @property
    def can_delete(self):
        return bool(self.evidence_ref and self.archived_status is not None
                    and self.archived_detail_readable and self.deleted_detail_is_404
                    and self.hard_delete_enabled and self.compatible_clients_verified and self.backup_restore_verified)


def validate_habit_list(records, contract, *, pages_complete=True):
    if not isinstance(records, list) or not pages_complete:
        raise ValueError('habit_list_incomplete')
    seen, accepted, unknown = set(), [], []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not record['id'].strip():
            raise ValueError('habit_list_invalid_id')
        if record['id'] in seen:
            raise ValueError('habit_list_duplicate_id')
        seen.add(record['id'])
        (unknown if contract.state(record) == 'unknown' else accepted).append(record)
    return accepted, unknown
