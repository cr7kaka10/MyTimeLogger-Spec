import json
from dataclasses import replace
from server.store import ServerSleepStore
from server.ticktick_config import begin_habit_round, habit_round_is_current, TickTickSettings
from server.habit_lifecycle_identity import local_habit_id, habit_aliases, same_binding


def test_binding_rounds_and_configuration_changes_are_fenced(tmp_path):
    store = ServerSleepStore(str(tmp_path / 'binding.db'))
    settings = TickTickSettings('private', 'dida365.com', 15, True)
    with store._transact() as conn:
        for uid in (1, 2):
            conn.execute("INSERT INTO users VALUES(?,?, 'x','now')", (uid, str(uid)))
            conn.execute("INSERT INTO server_system_config(user_id,key,value) VALUES(?,'ticktick_config',?)",
                         (uid, json.dumps({'access_token': settings.access_token, 'host': settings.host})))
        first = begin_habit_round(conn, 1, settings)
        assert habit_round_is_current(conn, 1, *first)
        second = begin_habit_round(conn, 1, settings)
        assert second == (first[0], first[1] + 1)
        assert not habit_round_is_current(conn, 1, *first)
        other = begin_habit_round(conn, 2, settings)
        assert other[0] != second[0]
        conn.execute("UPDATE server_system_config SET value='{}' WHERE user_id=1")
        assert not habit_round_is_current(conn, 1, *second)
        token_changed = begin_habit_round(conn, 1, replace(settings, access_token='new'))
        host_changed = begin_habit_round(conn, 1, replace(settings, host='ticktick.com'))
        assert len({first[0], token_changed[0], host_changed[0]}) == 3


def test_identity_never_collides_with_local_or_other_user():
    assert local_habit_id(1, 'local_x') == 'ticktick:1:local_x'
    assert habit_aliases(1, 'p') == ['ticktick:1:p', 'p']
    assert habit_aliases(1, 'local_x') == ['ticktick:1:local_x']
    row = dict(user_id=1, source='ticktick', provider_id='p', provider_binding_id='b')
    assert same_binding(row, 1, 'b')
    assert not same_binding(row, 2, 'b')
    assert not same_binding(row, 1, 'new')
    assert not same_binding({**row, 'provider_binding_id': None}, 1, 'b')
    assert not same_binding({**row, 'source': 'local'}, 1, 'b')
