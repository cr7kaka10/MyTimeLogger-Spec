"""纯判定：不存在经核实的归档读取契约时，404 永远只是待确认。"""
try:
    from .habit_lifecycle_identity import same_binding
except ImportError:
    from habit_lifecycle_identity import same_binding


def missing_candidates(rows, provider_ids, user_id, binding_id):
    return [row for row in rows if same_binding(row, user_id, binding_id)
            and row['provider_id'] not in provider_ids]


def detail_decision(row, detail, contract, *, user_id, binding_id, round_id,
                    current, auth_healthy, previous_missing_round=None):
    if not current or not same_binding(row, user_id, binding_id):
        return 'unresolved', 'stale_or_unverified_binding'
    observed = int(row.get('provider_observed_round') or 0)
    if observed >= round_id:
        return 'unresolved', 'newer_positive_fact'
    if detail.get('state') == 'present':
        record = detail.get('record') or {}
        if record.get('id') != row['provider_id']:
            return 'unresolved', 'detail_id_mismatch'
        state = contract.state(record)
        return (state, 'detail_positive') if state != 'unknown' else ('unresolved', 'unknown_status')
    if detail.get('status_code') != 404 or detail.get('state') != 'unresolved_missing':
        return 'unresolved', 'detail_failed'
    if not auth_healthy or not contract.can_delete:
        return 'unresolved', 'archive_detail_contract_unverified'
    if observed <= 0 or previous_missing_round is None or not observed < previous_missing_round < round_id:
        return 'unresolved', 'missing_confirmation_required'
    return 'deleted', 'verified_detail_404_twice'
