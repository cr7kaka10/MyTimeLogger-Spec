from server.store import ServerSleepStore


def test_backpack_events_are_scoped_and_discard_keeps_coin_balance(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u1','x','2026-08-01 00:00:00')")
        conn.execute("INSERT INTO users VALUES (2,'u2','x','2026-08-01 00:00:00')")
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, 10, 'seed', 'seed', 'seed')
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, -4, 'reward_buy', 'reward', 'item', '2026-08-04', 'discard-id')
        store.reward_wallet_service.append_ledger_in_txn(conn, 2, 0, 'reward_buy', 'reward', 'foreign', '2026-08-04', 'foreign-id')
    before = store.get_gold_balance(1)
    assert store.discard_backpack_item(2, 'discard-id')[0] is False
    assert store.discard_backpack_item(1, 'discard-id')[0] is True
    assert store.get_gold_balance(1) == before and store.list_backpack(1) == []
    events = store.list_backpack_events(1)
    assert [event['event_type'] for event in events] == ['discarded', 'acquired']
    assert len(store.list_backpack_events(1, limit=1, offset=1)) == 1
    assert [item['id'] for item in store.list_backpack(2)] == ['foreign-id']


def test_backpack_returns_the_authoritative_reward_description(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-08-01 00:00:00')")
        conn.execute(
            "INSERT INTO server_rewards (id,user_id,title,icon,price,description,is_active,created_at,updated_at) VALUES ('r',1,'商品','🎁',1,'创建时填写的说明',1,'2026-08-01 00:00:00','2026-08-01 00:00:00')"
        )
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, -1, 'reward_buy', 'r', '兑换商品成功', '2026-08-04', 'purchase')

    items = store.list_backpack(1)
    assert len(items) == 1
    assert items[0]['id'] == 'purchase'
    assert items[0]['description'] == '创建时填写的说明'

    assert store.update_reward(1, 'r', description='编辑后的说明')
    assert store.list_backpack(1)[0]['description'] == '编辑后的说明'
