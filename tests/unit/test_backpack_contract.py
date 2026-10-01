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


def test_period_item_freezes_expiry_and_rejects_use_at_boundary(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        conn.execute("""INSERT INTO server_habits
            (id,user_id,name,is_active,source,created_at,updated_at)
            VALUES('h',1,'习惯',0,'local','2026-10-01','2026-10-01')""")
    reward_id = store.create_reward(
        1, '月卡', price=0, unlock_source_type='habit', unlock_source_id='h',
        fulfillment_mode='fragment', fragment_target_count=1,
        inventory_mode='monthly', inventory_limit=10,
    )
    with store._transact() as conn:
        [ledger_id] = store.reward_settlement_service.grant_task_unlocks_in_txn(
            conn, 1, 'habit', 'h', 'oct:one', '习惯', '2026-10-01',
        )
    assert store.update_reward(1, reward_id, inventory_mode='unlimited', inventory_limit=None)
    with store._connect() as conn:
        assert conn.execute("SELECT expires_at FROM server_reward_ledger WHERE id=?", (ledger_id,)).fetchone()[0] == '2026-11-01 00:00:00'

    store.reward_wallet_service._now = lambda: '2026-11-01 00:00:00'
    assert store.use_backpack_item(1, ledger_id) == (False, '商品已过期')
    assert store.use_backpack_item(1, ledger_id) == (False, '商品已过期')
    with store._transact() as conn:
        store.reward_wallet_service.expire_backpack_items_in_txn(conn, 1)
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='backpack_use'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_backpack_events WHERE ledger_id=? AND event_type='backpack_expired'", (ledger_id,)).fetchone()[0] == 1
    assert store.list_backpack(1)[0]['is_expired'] is True
