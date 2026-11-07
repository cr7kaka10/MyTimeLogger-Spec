try:
    from ..ticktick_config import habit_round_is_current
except ImportError:
    from ticktick_config import habit_round_is_current
from .habit_lifecycle_events import publish


def observe_habit(conn, db, user_id, habit_id, binding_id, provider_id, round_id, state, now, publish_change=True):
    if state not in ('active', 'archived') or not habit_round_is_current(conn, user_id, binding_id, round_id):
        raise ValueError('stale_habit_observation')
    if conn.execute('SELECT 1 FROM server_habit_tombstones WHERE user_id=? AND habit_id=?', (user_id, habit_id)).fetchone():
        raise ValueError('deleted_habit_reappeared_requires_verification')
    row = conn.execute('SELECT * FROM server_habits WHERE user_id=? AND id=?', (user_id, habit_id)).fetchone()
    if not row or row['source'] != 'ticktick':
        raise ValueError('provider_habit_identity_conflict')
    if row['provider_binding_id'] == binding_id and row['provider_observed_round'] > round_id:
        raise ValueError('stale_habit_observation')
    archived = int(state == 'archived')
    changed = (row['is_active'] != archived or row['provider_binding_id'] != binding_id
               or (archived and row['archive_reason'] != 'provider_archived'))
    conn.execute('''UPDATE server_habits SET is_active=?,provider_binding_id=?,provider_id=?,
        provider_observed_round=?,archived_at=?,archive_reason=? WHERE user_id=? AND id=?''',
        (archived, binding_id, provider_id, round_id,
         (row['archived_at'] or now) if archived else None,
         'provider_archived' if archived else None, user_id, habit_id))
    conn.execute('DELETE FROM server_habit_probe_state WHERE user_id=? AND binding_id=? AND provider_id=?',
                 (user_id, binding_id, provider_id))
    if changed and publish_change:
        conn.execute('UPDATE server_habits SET updated_at=?,pushed_at=NULL WHERE user_id=? AND id=?', (now, user_id, habit_id))
        row = dict(conn.execute('SELECT * FROM server_habits WHERE user_id=? AND id=?', (user_id, habit_id)).fetchone())
        return publish(conn, db, user_id, 'server_habits', row)
    return int(row['lifecycle_version'])
