"""串行有界详情查询；状态仅由调用方在绑定/轮次复核后持久化。"""
import time
import httpx


async def probe_habits(client, candidates, states, *, budget=12, now=None):
    clock = time.time() if now is None else now
    queue = sorted(candidates, key=lambda row: (states.get(row['provider_id'], {}).get('last_probe_round', 0), row['provider_id']))
    results, updates = {}, {}
    requests, deferred = 0, 0
    for row in queue:
        pid = row['provider_id']
        state = states.get(pid, {})
        if requests >= max(0, min(int(budget), 12)) or state.get('retry_after', 0) > clock:
            deferred += 1
            continue
        requests += 1
        if hasattr(client, 'set_get_attempt_limit'):
            client.set_get_attempt_limit(1)
        try:
            results[pid] = await client.get_habit_detail(pid)
            updates[pid] = dict(retry_after=0, failures=0)
        except Exception as exc:
            code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            failures = min(int(state.get('failures', 0)) + 1, 10)
            results[pid] = dict(state='failed', status_code=code, error_type=type(exc).__name__)
            updates[pid] = dict(retry_after=clock + min(3600, 30 * 2 ** failures), failures=failures)
            if code in (401, 403, 429):
                deferred += len(queue) - requests - deferred
                break
    return results, updates, dict(detail_requests=requests, deferred_candidates=deferred)
