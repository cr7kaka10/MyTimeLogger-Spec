"""明确用户确认是逐对象证据，绝不解锁其他404候选的自动删除。"""
try:
    from ..ticktick_config import habit_round_is_current
    from ..habit_lifecycle_identity import provider_habit_id
except ImportError:
    from ticktick_config import habit_round_is_current
    from habit_lifecycle_identity import provider_habit_id
from .habit_lifecycle_delete import delete_verified_habit


def confirm_deleted_habit(conn, db, uid, target, binding, round_id, listed_ids, detail, confirmation_ref, now):
    if not confirmation_ref or not habit_round_is_current(conn, uid, binding, round_id):
        raise ValueError('habit_confirmation_stale')
    hid = target['id']
    pid = provider_habit_id(uid, hid)
    row = conn.execute('SELECT * FROM server_habits WHERE user_id=? AND id=?', (uid,hid)).fetchone()
    if not row:
        tomb = conn.execute('SELECT server_version FROM server_habit_tombstones WHERE user_id=? AND habit_id=?', (uid,hid)).fetchone()
        if tomb:
            return tomb[0]
        raise ValueError('habit_not_found')
    if (row['source'] != 'ticktick' or row['name'] != target['name'] or row['updated_at'] != target['updated_at']
            or row['provider_binding_id'] not in (None, '', binding)
            or (row['provider_id'] and row['provider_id'] != pid)):
        raise ValueError('habit_confirmation_identity_conflict')
    if (pid in listed_ids or detail.get('state') != 'unresolved_missing' or detail.get('status_code') != 404):
        raise ValueError('habit_confirmation_remote_conflict')
    # 只认领本次被用户明确确认且通过远端复核的旧行；不编造正向观察轮次。
    conn.execute('UPDATE server_habits SET provider_binding_id=?,provider_id=? WHERE user_id=? AND id=?', (binding,pid,uid,hid))
    current = conn.execute('SELECT * FROM server_habits WHERE user_id=? AND id=?', (uid,hid)).fetchone()
    evidence = f'user_confirmed_deleted:{confirmation_ref}'
    return delete_verified_habit(conn, db, current, binding, round_id, evidence, now)
