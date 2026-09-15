from server.store import ServerSleepStore


def test_backpack_events_include_readable_item_title_and_quantity(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1, 'u', 'x', '2026-08-04')")
        conn.execute("INSERT INTO server_rewards (id,user_id,title,price,created_at,updated_at) VALUES ('phone',1,'解锁手机*1',0,'2026-08-04','2026-08-04')")
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, 'reward_buy', 'phone', '购买', '2026-08-04', 'phone-ledger')
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, 'reward_buy', 'missing', '购买', '2026-08-04', 'missing-ledger')
    balance = store.get_gold_balance(1)
    assert store.use_backpack_item(1, 'phone-ledger')[0]
    events = store.list_backpack_events(1)
    assert events[0]['event_type'] == 'used' and events[0]['item_title'] == '解锁手机*1' and events[0]['quantity'] == 1
    assert any(event['item_title'] == '已下架奖励' and event['quantity'] == 1 for event in events)
    assert store.get_gold_balance(1) == balance
