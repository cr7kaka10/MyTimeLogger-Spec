import json
from server.db_wrapper import ServerDBWrapper
from server.sync_hub import SyncHub
from server.ticktick_config import begin_habit_round, TickTickSettings
from server.domain.habit_lifecycle_service import observe_habit
from server.domain.habit_lifecycle_delete import delete_habit
from server.domain.habit_lifecycle_restore import restore_habit
from server.domain.provider_habit_retirement import retire_provider_habits
from server.habit_lifecycle_pull import full_snapshot
from tests.unit.test_habit_local_reward_management import store
from tests.unit.test_habit_lifecycle_snapshot import CONTRACT


def test_archive_delete_full_snapshot_and_versioned_restore(store):
    db = ServerDBWrapper(); db.log_path = store.db_path
    settings = TickTickSettings('isolated', 'dida365.com', 15, True)
    with store._transact() as conn:
        conn.execute("INSERT INTO server_system_config(user_id,key,value,updated_at) VALUES(1,'ticktick_config',?,'now')",
                     (json.dumps(dict(access_token='isolated',host='dida365.com')),))
        conn.execute("UPDATE server_habits SET id='p',source='ticktick' WHERE id='local_h'")
        binding, round_id = begin_habit_round(conn, 1, settings)
        active = observe_habit(conn, db, 1, 'p', binding, 'p', round_id, 'active', '2026-09-23 20:00:00')
        _, round_id = begin_habit_round(conn, 1, settings)
        archive = observe_habit(conn, db, 1, 'p', binding, 'p', round_id, 'archived', '2026-09-23 20:01:00')
        assert archive > active
        assert conn.execute("SELECT is_active FROM server_habits WHERE id='p'").fetchone()[0] == 1
        _, round_id = begin_habit_round(conn, 1, settings)
        row = dict(conn.execute("SELECT * FROM server_habits WHERE id='p'").fetchone())
        deleted = delete_habit(conn, db, row, binding, round_id, CONTRACT, 'verified_detail_404_twice', '2026-09-23 20:02:00')
        assert deleted > archive and conn.execute("SELECT 1 FROM server_habits WHERE id='p'").fetchone() is None
        assert conn.execute('SELECT COUNT(*) FROM server_habit_tombstones').fetchone()[0] == 2
    with store._connect() as conn:
        tables, cutoff = full_snapshot(SyncHub(db), conn, 1)
        assert cutoff >= deleted
        assert {'p', 'ticktick:1:p'} <= {r['id'] for r in tables['habits'] if r.get('_sync_operation') == 'delete'}
    with store._transact() as conn:
        restored = restore_habit(conn, db, 1, 'p', 'isolated-restore-check', '2026-09-23 20:03:00')
        assert restored > deleted
        assert conn.execute('SELECT COUNT(*) FROM server_habit_tombstones').fetchone()[0] == 0
        assert conn.execute("SELECT restored_version FROM server_habits WHERE id='p'").fetchone()[0] == restored


def test_provider_habit_retirement_is_idempotent_and_preserves_history(store):
    db = ServerDBWrapper(); db.log_path = store.db_path
    with store._transact() as conn:
        conn.execute("UPDATE server_habits SET source='ticktick' WHERE id='local_h'")
        conn.execute("INSERT INTO server_habit_checkins(id,user_id,habit_id,status,updated_at) VALUES('c',1,'local_h',2,'now')")
        before_checkins = conn.execute("SELECT COUNT(*) FROM server_habit_checkins").fetchone()[0]
        first = retire_provider_habits(conn, db, 1, '2026-09-23 23:30:00')
        row = conn.execute("SELECT is_active,archive_reason,lifecycle_version FROM server_habits WHERE id='local_h'").fetchone()
        assert first['retired'] == 1 and first['remaining'] == 0
        assert tuple(row[:2]) == (1, 'provider_habit_sync_disabled')
        assert row[2] == first['boundary_version'] > 0
        assert conn.execute("SELECT COUNT(*) FROM server_habit_checkins").fetchone()[0] == before_checkins
    with store._transact() as conn:
        second = retire_provider_habits(conn, db, 1, '2026-09-23 23:31:00')
        assert second['retired'] == 0 and second['boundary_version'] == 0
