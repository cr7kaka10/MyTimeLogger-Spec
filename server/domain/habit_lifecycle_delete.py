import json
try:
    from ..ticktick_config import habit_round_is_current
    from ..habit_lifecycle_identity import habit_aliases
except ImportError:
    from ticktick_config import habit_round_is_current
    from habit_lifecycle_identity import habit_aliases
from .habit_lifecycle_events import publish
from .habit_lifecycle_audit import freeze_habit


def delete_habit(conn, db, row, binding_id, round_id, contract, evidence, now):
    uid, hid = row['user_id'], row['id']
    existing = conn.execute('SELECT server_version FROM server_habit_tombstones WHERE user_id=? AND habit_id=?', (uid,hid)).fetchone()
    if existing:
        return existing[0]
    if (not contract.can_delete or evidence != 'verified_detail_404_twice'
            or not habit_round_is_current(conn, uid, binding_id, round_id)):
        raise ValueError('habit_delete_evidence_unverified')
    current = conn.execute('SELECT * FROM server_habits WHERE user_id=? AND id=?', (uid,hid)).fetchone()
    if (not current or current['source'] != 'ticktick' or current['provider_binding_id'] != binding_id
            or current['provider_observed_round'] >= round_id):
        raise ValueError('habit_delete_identity_conflict')
    return delete_verified_habit(conn, db, current, binding_id, round_id, evidence, now)


def delete_verified_habit(conn, db, current, binding_id, round_id, evidence, now):
    """内部事务实现；调用者必须先完成自动契约或逐对象用户确认校验。"""
    uid, hid = current['user_id'], current['id']
    snapshot = freeze_habit(conn, current, now)
    for child in snapshot['checkins']:
        conn.execute('DELETE FROM server_habit_checkins WHERE user_id=? AND id=?', (uid,child['id']))
        publish(conn, db, uid, 'server_habit_checkins', child, 'delete')
    for binding in snapshot['bindings']:
        conn.execute('DELETE FROM server_reward_source_bindings WHERE user_id=? AND id=?', (uid,binding['id']))
        publish(conn, db, uid, 'server_reward_source_bindings', binding, 'delete')
    conn.execute('DELETE FROM server_habits WHERE user_id=? AND id=?', (uid,hid))
    payload = dict(id=hid, source='ticktick', provider_binding_id=binding_id,
                   provider_id=current['provider_id'], deleted_at=now, evidence=evidence)
    aliases = habit_aliases(uid, current['provider_id'])
    for alias in aliases:
        if alias != hid and conn.execute('SELECT 1 FROM server_habits WHERE user_id=? AND id=?', (uid,alias)).fetchone():
            raise ValueError('habit_alias_collision')
        version = publish(conn, db, uid, 'server_habits', {**payload, 'id':alias}, 'delete')
        conn.execute('INSERT INTO server_habit_tombstones VALUES(?,?,?,?,?,?,?,?,?)',
            (uid,alias,binding_id,current['provider_id'],now,evidence,version,round_id,json.dumps(aliases)))
    return version
