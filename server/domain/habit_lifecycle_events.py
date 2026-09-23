import json


def publish(conn, db, user_id, table, row, operation='upsert'):
    payload = dict(row)
    version = db.write_server_change(user_id, table.removeprefix('server_'), str(row['id']),
        operation, payload, table_name=table, device_id='habit-lifecycle', conn=conn)
    payload['server_version'] = version
    if table == 'server_habits':
        payload['lifecycle_version'] = version
        if operation != 'delete':
            conn.execute('UPDATE server_habits SET lifecycle_version=? WHERE user_id=? AND id=?',
                         (version, user_id, row['id']))
    conn.execute('UPDATE server_change_log SET changed_fields_json=? WHERE user_id=? AND server_version=?',
                 (json.dumps(payload, ensure_ascii=False), user_id, version))
    return version
