import json

import pytest

import server.domain.reward_rebuild_service as rebuild_module
from server.domain.reward_rebuild_service import RewardRebuildError, RewardRebuildService
from server.store import ServerSleepStore


def _case(tmp_db_path, monkeypatch, event_type, *, fragment_id="frag", reward_id="reward", quantity=1, fragments=(), composed_purchase=True):
    store = ServerSleepStore(db_path=tmp_db_path)
    service = RewardRebuildService(store)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p','2026-08-25')")
        for row in fragments:
            if int(row[1]) != 1:
                conn.execute("INSERT OR IGNORE INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)", (int(row[1]), f'u{row[1]}', 'p', '2026-08-25'))
            if str(row[2]) != reward_id:
                conn.execute("INSERT OR IGNORE INTO server_rewards(id,user_id,title,price,is_active,redemption_mode,fulfillment_mode,fragment_target_count,fragment_rule_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (str(row[2]), int(row[1]), '其他奖励', 0, 1, 'task', 'fragment', 1, 1, '2026-08-25', '2026-08-25'))
        conn.execute("INSERT INTO server_rewards(id,user_id,title,price,is_active,redemption_mode,fulfillment_mode,fragment_target_count,fragment_rule_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (reward_id, 1, '奖励', 0, 1, 'task', 'fragment', max(1, quantity), 1, '2026-08-25', '2026-08-25'))
        conn.execute("INSERT INTO server_reward_ledger VALUES('old',1,2,'manual_adjustment','old','旧账','2026-08-25','2026-08-25 00:00:00','2026-08-25','2026-08-25',NULL)")
        store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, 1, lambda: '2026-08-25')
        snapshot = service._snapshot(conn, 1)
        frozen = service._revision(conn, 1)
        conn.execute("INSERT INTO server_reward_rebuild_jobs(id,user_id,status,statistics_start_date,preview_hash,frozen_revision,trace_id,created_at,updated_at) VALUES('job',1,'queued','2026-08-01','hash',?,'trace','2026-08-25','2026-08-25')", (frozen,))
        conn.execute("INSERT INTO server_reward_rebuild_snapshots(job_id,user_id,epoch,snapshot_json,created_at) VALUES('job',1,0,?,'2026-08-25')", (json.dumps(snapshot),))

    class FakeBuilder:
        def __init__(self, candidate_store):
            self.store = candidate_store

        def build(self, user_id, start_date):
            with self.store._transact() as conn:
                for table in ("server_backpack_events", "server_reward_fragments", "server_user_wallets", "server_external_rewards", "server_reward_ledger"):
                    conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
                conn.execute("INSERT INTO server_user_wallets(user_id,balance,updated_at) VALUES(1,0,'2026-08-25')")
                if event_type == 'fragment_composed' and composed_purchase:
                    conn.execute("INSERT INTO server_reward_ledger VALUES('composed-buy',1,0,'reward_buy',?,'合成','2026-08-25','2026-08-25','2026-08-25','2026-08-25',NULL)", (f'unlock:{reward_id}:fragment:{fragment_id}',))
                for row in fragments:
                    conn.execute("INSERT INTO server_reward_fragments(id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,issued_at,expires_at,status,compose_batch_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
                conn.execute("INSERT INTO server_backpack_events(id,user_id,ledger_id,event_type,reward_id,fragment_id,quantity,created_at) VALUES('event',1,'missing',?,?,?,?,?)", (event_type, reward_id, fragment_id, quantity, '2026-08-25'))
            return {"ledger_rows": 0, "balance": 0, "skipped": []}

    monkeypatch.setattr(rebuild_module, "RewardCandidateBuilder", FakeBuilder)
    return store, service


def _fragment_row(fragment_id, reward_id="reward", status="expired", batch=None):
    return (fragment_id, 1, reward_id, 'habit', 'habit-1', f'habit:habit-1:{fragment_id}', 1, '2026-08-20', '2026-08-27', status, batch, '2026-08-20', '2026-08-20')


@pytest.mark.parametrize("event_type,status", [("fragment_acquired", "active"), ("fragment_acquired", "consumed"), ("fragment_expired", "expired"), ("fragment_revoked", "revoked")])
def test_single_fragment_lifecycle_events_publish(tmp_db_path, monkeypatch, event_type, status):
    store, service = _case(tmp_db_path, monkeypatch, event_type, fragments=(_fragment_row('frag', status=status),))
    report = service.build_and_publish(1, 'job', {"ok": True})
    assert report["balance"] == 0
    with store._connect() as conn:
        assert conn.execute("SELECT event_type FROM server_backpack_events WHERE id='event'").fetchone()[0] == event_type


def test_composed_fragment_batch_requires_matching_consumed_fragments(tmp_db_path, monkeypatch):
    rows = (_fragment_row('a', status='consumed', batch='batch'), _fragment_row('b', status='consumed', batch='batch'))
    store, service = _case(tmp_db_path, monkeypatch, 'fragment_composed', fragment_id='batch', quantity=2, fragments=rows)
    assert service.build_and_publish(1, 'job', {"ok": True})["balance"] == 0
    with store._connect() as conn:
        assert conn.execute("SELECT event_type FROM server_backpack_events WHERE id='event'").fetchone()[0] == 'fragment_composed'


def test_composed_fragment_requires_reward_buy(tmp_db_path, monkeypatch):
    rows = (_fragment_row('a', status='consumed', batch='batch'),)
    store, service = _case(tmp_db_path, monkeypatch, 'fragment_composed', fragment_id='batch', fragments=rows, composed_purchase=False)
    with pytest.raises(RewardRebuildError) as failure:
        service.build_and_publish(1, 'job', {"ok": True})
    assert failure.value.reward_rebuild_details["check"] == 'invalid_composed_fragment_event'


@pytest.mark.parametrize("event_type,fragment_id,quantity,fragments,check", [
    ('fragment_expired', 'missing', 1, (), 'orphan_fragment_backpack_event'),
    ('fragment_composed', 'missing-batch', 1, (), 'invalid_composed_fragment_event'),
    ('fragment_composed', 'batch', 2, (_fragment_row('a', status='consumed', batch='batch'),), 'invalid_composed_fragment_event'),
    ('fragment_composed', 'batch', 0, (_fragment_row('a', status='consumed', batch='batch'),), 'invalid_composed_fragment_event'),
    ('fragment_composed', 'batch', 1, (_fragment_row('a', status='active', batch='batch'),), 'invalid_composed_fragment_event'),
    ('fragment_future', 'frag', 1, (_fragment_row('frag'),), 'unknown_fragment_backpack_event'),
    ('fragment_expired', 'frag', 1, (_fragment_row('frag', reward_id='other'),), 'orphan_fragment_backpack_event'),
    ('fragment_expired', 'frag', 1, ((_fragment_row('frag'))[:1] + (2,) + (_fragment_row('frag'))[2:],), 'orphan_fragment_backpack_event'),
])
def test_invalid_fragment_references_restore_old_ledger(tmp_db_path, monkeypatch, event_type, fragment_id, quantity, fragments, check):
    store, service = _case(tmp_db_path, monkeypatch, event_type, fragment_id=fragment_id, quantity=quantity, fragments=fragments)
    with pytest.raises(RewardRebuildError) as failure:
        service.build_and_publish(1, 'job', {"ok": True})
    assert failure.value.reward_rebuild_details["check"] == check
    service.fail_and_restore(1, 'job', failure.value)
    with store._connect() as conn:
        assert conn.execute("SELECT id FROM server_reward_ledger WHERE id='old'").fetchone()[0] == 'old'
