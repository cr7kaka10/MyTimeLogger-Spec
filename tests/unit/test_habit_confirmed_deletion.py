import json
import pytest
from server.db_wrapper import ServerDBWrapper
from server.ticktick_config import begin_habit_round, TickTickSettings
from server.domain.habit_confirmed_deletion import confirm_deleted_habit
from tests.unit.test_habit_local_reward_management import store


@pytest.mark.parametrize('conflict', ['none', 'name', 'source', 'listed', 'detail', 'binding', 'version'])
def test_user_confirmation_is_targeted_and_transactional(store, conflict):
    db = ServerDBWrapper(); db.log_path = store.db_path
    with store._transact() as conn:
        conn.execute("INSERT INTO server_system_config(user_id,key,value,updated_at) VALUES(1,'ticktick_config',?,'now')",
                     (json.dumps(dict(access_token='test',host='dida365.com')),))
        binding, round_id = begin_habit_round(conn, 1, TickTickSettings('test','dida365.com',15,True))
        conn.execute("UPDATE server_habits SET id='ticktick:1:p',source='ticktick' WHERE id='local_h'")
        target = dict(conn.execute("SELECT * FROM server_habits WHERE user_id=1 AND id='ticktick:1:p'").fetchone())
        if conflict in ('name', 'version'):
            target['name' if conflict == 'name' else 'updated_at'] = 'old'
        if conflict == 'source': conn.execute("UPDATE server_habits SET source='local' WHERE id=?", (target['id'],))
        if conflict == 'binding': conn.execute("UPDATE server_habits SET provider_binding_id='other' WHERE id=?", (target['id'],))
        detail = dict(state='unresolved_missing', status_code=404 if conflict != 'detail' else 500)
        listed = {'p'} if conflict == 'listed' else set()
        args = (conn,db,1,target,binding,round_id,listed,detail,'isolated-user-confirmation','2026-09-23 21:00:00')
        if conflict != 'none':
            with pytest.raises(ValueError): confirm_deleted_habit(*args)
            assert conn.execute('SELECT COUNT(*) FROM server_habit_tombstones').fetchone()[0] == 0
        else:
            version = confirm_deleted_habit(*args)
            assert version > 0
            assert conn.execute('SELECT COUNT(*) FROM server_habits WHERE user_id=1').fetchone()[0] == 0
            assert conn.execute('SELECT COUNT(*) FROM server_habit_tombstones WHERE user_id=1').fetchone()[0] == 2
            assert conn.execute('SELECT COUNT(*) FROM server_habit_frozen_audit WHERE user_id=1').fetchone()[0] == 1
            assert confirm_deleted_habit(*args) == version - 1
