import asyncio
import pytest
from server.db_wrapper import ServerDBWrapper
from server.sync_hub import SyncHub
from tests.unit.test_habit_local_reward_management import store


@pytest.mark.parametrize('scope', ['core', 'checklist'])
@pytest.mark.parametrize('deleted', [False, True])
def test_provider_lifecycle_cannot_be_spoofed_by_old_push(store, scope, deleted):
    with store._transact() as conn:
        conn.execute("UPDATE server_habits SET source='ticktick',is_active=1 WHERE id='local_h'")
        if deleted:
            conn.execute("INSERT INTO server_habit_tombstones VALUES(1,'local_h','b','p','now','explicit',1,1,'[]')")
            conn.execute("DELETE FROM server_habits WHERE id='local_h'")
    db = ServerDBWrapper(); db.log_path = store.db_path
    result = asyncio.run(SyncHub(db).handle_push([dict(table='habits', change_id='old',
        record=dict(id='local_h', name='revive', source='local', is_active=0))], 1, scope))
    assert result['accepted'] == 0
    reason = result['operation_results'][0]['reason']
    assert reason == ('habit_deleted' if deleted else 'provider_habit_readonly')
    with store._connect() as conn:
        row = conn.execute("SELECT is_active FROM server_habits WHERE id='local_h'").fetchone()
        assert row is None if deleted else row[0] == 1


def test_rest_local_edit_archive_and_provider_protection(store):
    hid = store.create_habit(1, '新建')
    assert hid.startswith('local_')
    assert store.update_habit(1, hid, name='改名')
    assert store.update_habit(1, hid, is_active=1)
    with pytest.raises(ValueError, match='habit_archived'):
        store.update_habit(1, hid, is_active=0)
    with store._transact() as conn:
        conn.execute("UPDATE server_habits SET source='ticktick' WHERE id='local_h'")
    with pytest.raises(ValueError, match='provider_habit_readonly'):
        store.update_habit(1, 'local_h', name='修改镜像')
