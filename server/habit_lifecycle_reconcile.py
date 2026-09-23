try:
    from .habit_lifecycle_snapshot import missing_candidates, detail_decision
    from .habit_lifecycle_probe import probe_habits
    from .habit_lifecycle_identity import provider_habit_id
    from .ticktick_config import habit_round_is_current
    from .domain.habit_lifecycle_service import observe_habit
    from .domain.habit_lifecycle_delete import delete_habit
except ImportError:
    from habit_lifecycle_snapshot import missing_candidates, detail_decision
    from habit_lifecycle_probe import probe_habits
    from habit_lifecycle_identity import provider_habit_id
    from ticktick_config import habit_round_is_current
    from domain.habit_lifecycle_service import observe_habit
    from domain.habit_lifecycle_delete import delete_habit


async def reconcile_missing(hub, client, uid, binding, round_id, listed, contract, now):
    with hub._conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM server_habits WHERE user_id=? AND source='ticktick'", (uid,))]
        states = {r['provider_id']: dict(r) for r in conn.execute('SELECT * FROM server_habit_probe_state WHERE user_id=? AND binding_id=?', (uid,binding))}
    candidates = missing_candidates(rows, listed, uid, binding)
    # 未核实旧行也可只读探测；只能用相同 ID 的正向详情认领新绑定，404 不认领。
    unverified = [{**r, 'provider_id': r['provider_id'] or provider_habit_id(uid,r['id'])} for r in rows if r['provider_binding_id'] != binding]
    candidates += [r for r in unverified if r['provider_id'] not in listed]
    details, updates, stats = await probe_habits(client, candidates, states)
    stats.update(unresolved_missing=0, lifecycle_deleted=0, lifecycle_archived=0,
                 unverified_missing=sum(r['provider_id'] not in listed for r in unverified), list_coverage_anomalies=0)
    with hub._transact() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not habit_round_is_current(conn, uid, binding, round_id):
            raise ValueError('stale_habit_round')
        for row in candidates:
            pid = row['provider_id']; detail = details.get(pid, {})
            state, reason = detail_decision(row, detail, contract, user_id=uid, binding_id=binding,
                round_id=round_id, current=True, auth_healthy=bool(listed), previous_missing_round=states.get(pid, {}).get('missing_round'))
            if row['provider_binding_id'] != binding and detail.get('state') == 'present':
                record = detail.get('record') or {}
                if record.get('id') == pid and contract.state(record) != 'unknown':
                    state = contract.state(record)
                    stats['unverified_missing'] -= 1
            if state == 'deleted':
                delete_habit(conn, hub.db, row, binding, round_id, contract, reason, now)
                stats['lifecycle_deleted'] += 1
            elif state in ('active', 'archived'):
                observe_habit(conn, hub.db, uid, row['id'], binding, pid, round_id, state, now)
                stats['lifecycle_archived'] += int(state == 'archived')
                stats['list_coverage_anomalies'] += int(state == 'active')
            else:
                stats['unresolved_missing'] += 1
            if pid not in updates or state in ('active', 'archived', 'deleted'):
                continue
            missing = states.get(pid, {}).get('missing_round') if detail.get('status_code') == 404 else None
            missing = missing or (round_id if detail.get('status_code') == 404 else None)
            conn.execute('''INSERT INTO server_habit_probe_state VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,binding_id,provider_id)
                DO UPDATE SET missing_round=excluded.missing_round,last_probe_round=excluded.last_probe_round,retry_after=excluded.retry_after,failures=excluded.failures''',
                (uid,binding,pid,missing,round_id,updates[pid]['retry_after'],updates[pid]['failures']))
    return stats
