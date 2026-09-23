import json


def tombstone_payload(row):
    return dict(id=row['habit_id'], source='ticktick', provider_binding_id=row['binding_id'],
        provider_id=row['provider_id'], deleted_at=row['deleted_at'], evidence=row['evidence'],
        server_version=row['server_version'], lifecycle_version=row['server_version'], _sync_operation='delete')


def full_snapshot(hub, conn, uid):
    try:
        from .sync_sql_allowlist import SYNC_TABLES, SYNC_TABLE_SET
    except ImportError:
        from sync_sql_allowlist import SYNC_TABLES, SYNC_TABLE_SET
    conn.execute('BEGIN')
    counter = conn.execute('SELECT current_version FROM server_version_counters WHERE user_id=?', (uid,)).fetchone()
    cutoff = int(counter[0]) if counter else 0
    tables = {t: hub.get_changes_since(t, None, uid, conn=conn) for t in SYNC_TABLES}
    deletes = conn.execute('''SELECT c.* FROM server_change_log c WHERE c.user_id=? AND c.operation='delete'
        AND c.server_version<=? AND NOT EXISTS(SELECT 1 FROM server_change_log n WHERE n.user_id=c.user_id
        AND n.table_name=c.table_name AND n.record_id=c.record_id AND n.server_version>c.server_version)''', (uid,cutoff))
    for row in deletes:
        table = row['table_name'].removeprefix('server_')
        if table in SYNC_TABLE_SET:
            payload = json.loads(row['changed_fields_json'] or '{}')
            tables[table].append({**payload, 'id':row['record_id'], '_sync_operation':'delete', 'server_version':row['server_version']})
    for row in conn.execute('SELECT * FROM server_habit_tombstones WHERE user_id=?', (uid,)):
        tables['habits'].append(tombstone_payload(row))
    return {k:v for k,v in tables.items() if v}, cutoff


def habit_event_payload(change, current):
    payload = json.loads(change.get('changed_fields_json') or '{}')
    if payload.get('lifecycle_version'):
        return payload
    if current and current.get('lifecycle_version'):
        return current
    return current  # 迁移前的旧事件未声明对象版本，不冒用旧事件版本。
