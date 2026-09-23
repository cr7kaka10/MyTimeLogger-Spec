"""定点恢复入口。仅供运维在核实源端及来源绑定后调用，不暴露给普通客户端。"""
import json
from .habit_lifecycle_events import publish


def restore_habit(conn, db, uid, hid, evidence_ref, now):
    if not evidence_ref:
        raise ValueError('verified_restore_evidence_required')
    conn.execute('BEGIN IMMEDIATE')
    audit = conn.execute('SELECT * FROM server_habit_frozen_audit WHERE user_id=? AND habit_id=?', (uid,hid)).fetchone()
    binding = conn.execute('SELECT binding_id FROM server_habit_provider_bindings WHERE user_id=?', (uid,)).fetchone()
    if not audit or not binding or audit['binding_id'] != binding[0]:
        raise ValueError('restore_binding_unverified')
    snapshot = json.loads(audit['snapshot_json'])
    if snapshot.get('restored_at'):
        return None
    row = snapshot['habit']
    if conn.execute('SELECT 1 FROM server_habits WHERE user_id=? AND id=?', (uid,hid)).fetchone():
        raise ValueError('restore_target_exists')
    for table, records in [('server_habits',[row]), ('server_habit_checkins',snapshot['checkins']),
                           ('server_reward_source_bindings',snapshot['bindings'])]:
        for record in records:
            values = {**record, 'updated_at':now}
            cols = list(values)
            conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", tuple(values[c] for c in cols))
            if table != 'server_habits':
                publish(conn, db, uid, table, values)
    version = publish(conn, db, uid, 'server_habits', {**row,'updated_at':now,'_lifecycle_restore':True})
    conn.execute('UPDATE server_habits SET restored_version=? WHERE user_id=? AND id=?', (version,uid,hid))
    conn.execute('DELETE FROM server_habit_tombstones WHERE user_id=? AND binding_id=? AND provider_id=?', (uid,audit['binding_id'],row['provider_id']))
    snapshot.update(restored_at=now, restore_evidence=evidence_ref)
    conn.execute('UPDATE server_habit_frozen_audit SET snapshot_json=?,created_at=? WHERE user_id=? AND habit_id=?',
                 (json.dumps(snapshot,ensure_ascii=False),now,uid,hid))
    return version
