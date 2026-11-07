import json


def freeze_habit(conn, row, now):
    uid, hid = row['user_id'], row['id']
    read = lambda sql, args: [dict(r) for r in conn.execute(sql, args).fetchall()]
    bindings = read("SELECT * FROM server_reward_source_bindings WHERE user_id=? AND source_type='habit' AND source_id=?", (uid, hid))
    rewards = {r['reward_id'] for r in bindings}
    ledger = read('SELECT * FROM server_reward_ledger WHERE user_id=?', (uid,))
    selected = [r for r in ledger if (r['source_type'] in ('habit_checkin','habit_fail') and str(r['source_id']) == hid)
                or (r['source_type'] == 'reward_buy' and any(str(r['source_id']).startswith(p) for rid in rewards
                    for p in [f'unlock:{rid}:habit:habit:{hid}:', f'unlock:{rid}:habit:threshold:']))]
    snapshot = dict(habit=dict(row), bindings=bindings,
        checkins=read('SELECT * FROM server_habit_checkins WHERE user_id=? AND habit_id=?', (uid,hid)),
        ledger=selected,
        fragments=read("SELECT * FROM server_reward_fragments WHERE user_id=? AND source_type='habit' AND source_id=?", (uid,hid)))
    conn.execute('''INSERT INTO server_habit_frozen_audit VALUES(?,?,?,?,?) ON CONFLICT(user_id,habit_id)
        DO UPDATE SET binding_id=excluded.binding_id,snapshot_json=excluded.snapshot_json,created_at=excluded.created_at''',
                 (uid,hid,row['provider_binding_id'],json.dumps(snapshot,ensure_ascii=False),now))
    return snapshot
