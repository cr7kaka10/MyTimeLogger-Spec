"""重建时保留已物理删除来源的结算，不把来源删除当作取消历史。"""
import json
from contextlib import contextmanager


@contextmanager
def preserve_frozen_habits(conn, uid, start_date):
    snapshots = [json.loads(r[0]) for r in conn.execute('SELECT snapshot_json FROM server_habit_frozen_audit WHERE user_id=?', (uid,))]
    snapshots = [s for s in snapshots if not s.get('restored_at')]
    reward_ids = {r['reward_id'] for s in snapshots for r in s.get('bindings', []) + s.get('fragments', [])}
    read = lambda table: [dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE user_id=?', (uid,))]
    current_ledger = read('server_reward_ledger') if snapshots else []
    by_id = {r['id']:r for r in current_ledger}
    frozen_coins = [by_id.get(r['id'],r) for s in snapshots for r in s['ledger']
                    if r['source_type'] in ('habit_checkin','habit_fail') and str(r.get('target_date') or '') >= start_date]
    goods = [r for r in current_ledger if r['source_type'] == 'reward_buy'
             and any(str(r['source_id']).startswith(f'unlock:{rid}:') for rid in reward_ids)]
    acquired = {r['id'] for r in goods}
    fragments = [r for r in read('server_reward_fragments') if r['reward_id'] in reward_ids] if snapshots else []
    events = [r for r in read('server_backpack_events') if r.get('reward_id') in reward_ids or r['ledger_id'] in acquired] if snapshots else []
    bindings = [r for r in read('server_reward_source_bindings') if r['reward_id'] in reward_ids] if snapshots else []
    def insert(table, rows):
        for row in rows:
            keys = list(row)
            conn.execute(f"INSERT OR IGNORE INTO {table} ({','.join(keys)}) VALUES({','.join('?' for _ in keys)})", tuple(row[k] for k in keys))
    def restore():
        insert('server_reward_ledger', frozen_coins + goods)
        insert('server_reward_fragments', fragments)
        insert('server_backpack_events', events)
        # 同商品的其他来源不能在本次重建重复合成/发奖；候选生成后恢复绑定。
        for row in bindings:
            conn.execute('DELETE FROM server_reward_source_bindings WHERE user_id=? AND id=?', (uid,row['id']))
    try:
        yield restore
    finally:
        insert('server_reward_source_bindings', bindings)
