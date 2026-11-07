from .habit_lifecycle_events import publish


RETIREMENT_REASON = 'provider_habit_sync_disabled'


def retire_provider_habits(conn, db, user_id: int, now: str, limit: int = 200) -> dict:
    rows = conn.execute('''SELECT * FROM server_habits
        WHERE user_id=? AND is_active=0 AND (source='ticktick' OR provider_binding_id IS NOT NULL)
        ORDER BY updated_at,id LIMIT ?''', (user_id, limit)).fetchall()
    retired = 0
    latest_version = 0
    for source in rows:
        conn.execute('''UPDATE server_habits SET is_active=1,archived_at=?,archive_reason=?,
            updated_at=?,pushed_at=NULL WHERE user_id=? AND id=? AND is_active=0''',
            (now, RETIREMENT_REASON, now, user_id, source['id']))
        if not conn.execute('SELECT changes()').fetchone()[0]:
            continue
        row = dict(conn.execute('SELECT * FROM server_habits WHERE user_id=? AND id=?',
                                (user_id, source['id'])).fetchone())
        latest_version = publish(conn, db, user_id, 'server_habits', row)
        retired += 1
    remaining = conn.execute('''SELECT COUNT(*) FROM server_habits
        WHERE user_id=? AND is_active=0 AND (source='ticktick' OR provider_binding_id IS NOT NULL)''',
        (user_id,)).fetchone()[0]
    return {'status': 'disabled', 'reason': RETIREMENT_REASON, 'retired': retired,
            'remaining': int(remaining), 'boundary_version': latest_version}
