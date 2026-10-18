import json
import sqlite3

import pytest

import server.domain.reward_rebuild_service as rebuild_module
from server.domain.reward_rebuild_service import RewardRebuildError, RewardRebuildService
from server.store import ServerSleepStore


def _case(tmp_db_path, monkeypatch, event_type, *, fragment_id="frag", reward_id="reward", quantity=1,
          fragments=(), composed_purchase=True, required_units=None, provenance_kind="exact"):
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
        conn.execute(
            """INSERT INTO server_reward_ledger(
                id,user_id,amount,source_type,source_id,description,target_date,
                occurred_at,expires_at,created_at,updated_at,pushed_at
            ) VALUES('old',1,2,'manual_adjustment','old','旧账','2026-08-25',
                '2026-08-25 00:00:00',NULL,'2026-08-25','2026-08-25',NULL)"""
        )
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
                for table in ("server_reward_fragment_contributions", "server_reward_fragment_batches", "server_backpack_events", "server_reward_fragments", "server_user_wallets", "server_external_rewards", "server_reward_ledger"):
                    conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
                conn.execute("INSERT INTO server_user_wallets(user_id,balance,updated_at) VALUES(1,0,'2026-08-25')")
                if event_type == 'fragment_composed' and composed_purchase:
                    conn.execute(
                        """INSERT INTO server_reward_ledger(
                            id,user_id,amount,source_type,source_id,description,target_date,
                            occurred_at,expires_at,created_at,updated_at,pushed_at
                        ) VALUES('composed-buy',1,0,'reward_buy',?,'合成','2026-08-25',
                            '2026-08-25',NULL,'2026-08-25','2026-08-25',NULL)""",
                        (f'unlock:{reward_id}:fragment:{fragment_id}',),
                    )
                for row in fragments:
                    conn.execute("""INSERT INTO server_reward_fragments(
                        id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
                        fragment_measure_mode,progress_units,consumed_units,issued_at,expires_at,status,
                        compose_batch_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
                if event_type == 'fragment_composed':
                    threshold = max(1, int(required_units or len(fragments) or 1))
                    conn.execute("""INSERT INTO server_reward_fragment_batches VALUES
                        ('candidate-batch',1,?,?,1,'count',?,?, 'composed-buy','2026-08-25',?,'2026-08-25','2026-08-25')""",
                        (fragment_id, reward_id, threshold, max(1, quantity), provenance_kind))
                    if provenance_kind == 'exact':
                        for index, row in enumerate(fragments):
                            conn.execute("""INSERT INTO server_reward_fragment_contributions VALUES
                                (?,1,?,?,1,0,1,'2026-08-25')""", (f'contribution:{index}', fragment_id, row[0]))
                conn.execute("INSERT INTO server_backpack_events(id,user_id,ledger_id,event_type,reward_id,fragment_id,quantity,created_at) VALUES('event',1,'missing',?,?,?,?,?)", (event_type, reward_id, fragment_id, quantity, '2026-08-25'))
            return {"ledger_rows": 0, "balance": 0, "skipped": []}

    monkeypatch.setattr(rebuild_module, "RewardCandidateBuilder", FakeBuilder)
    return store, service


def _fragment_row(fragment_id, reward_id="reward", status="expired", batch=None, progress=1):
    consumed = progress if status == "consumed" else 0
    return (fragment_id, 1, reward_id, 'habit', 'habit-1', f'habit:habit-1:{fragment_id}', 1,
            'count', progress, consumed, '2026-08-20', '2026-08-27', status, batch,
            '2026-08-20', '2026-08-20')


@pytest.mark.parametrize("event_type,status", [("fragment_acquired", "active"), ("fragment_acquired", "consumed"), ("fragment_expired", "expired"), ("fragment_revoked", "revoked")])
def test_single_fragment_lifecycle_events_publish(tmp_db_path, monkeypatch, event_type, status):
    store, service = _case(tmp_db_path, monkeypatch, event_type, fragments=(_fragment_row('frag', status=status),))
    report = service.build_and_publish(1, 'job', {"ok": True})
    assert report["balance"] == 0
    with store._connect() as conn:
        assert conn.execute("SELECT event_type FROM server_backpack_events WHERE id='event'").fetchone()[0] == event_type


def test_composed_fragment_batch_requires_matching_consumed_fragments(tmp_db_path, monkeypatch):
    rows = (_fragment_row('a', status='consumed', batch='batch'), _fragment_row('b', status='consumed', batch='batch'))
    store, service = _case(tmp_db_path, monkeypatch, 'fragment_composed', fragment_id='batch', quantity=1, fragments=rows)
    assert service.build_and_publish(1, 'job', {"ok": True})["balance"] == 0
    with store._connect() as conn:
        assert conn.execute("SELECT event_type FROM server_backpack_events WHERE id='event'").fetchone()[0] == 'fragment_composed'


def test_composed_fragment_requires_reward_buy(tmp_db_path, monkeypatch):
    rows = (_fragment_row('a', status='consumed', batch='batch'),)
    store, service = _case(tmp_db_path, monkeypatch, 'fragment_composed', fragment_id='batch', fragments=rows, composed_purchase=False)
    with pytest.raises(RewardRebuildError) as failure:
        service.build_and_publish(1, 'job', {"ok": True})
    assert failure.value.reward_rebuild_details["check"] == 'invalid_composed_fragment_event'


def test_seven_fragment_units_validate_one_output_and_legacy_needs_no_rows(tmp_db_path, monkeypatch):
    rows = tuple(_fragment_row(str(index), status='consumed', batch='batch') for index in range(7))
    store, service = _case(tmp_db_path, monkeypatch, 'fragment_composed', fragment_id='batch', fragments=rows)
    assert service.build_and_publish(1, 'job', {"ok": True})["balance"] == 0
    legacy_store, legacy_service = _case(str(tmp_db_path) + '-legacy', monkeypatch, 'fragment_composed',
                                         fragment_id='legacy', fragments=(), provenance_kind='legacy_attested')
    assert legacy_service.build_and_publish(1, 'job', {"ok": True})["balance"] == 0


def test_publish_failure_restores_old_ledger_and_fragment_provenance(tmp_db_path, monkeypatch):
    rows = (_fragment_row('a', status='consumed', batch='batch'),)
    store, service = _case(tmp_db_path, monkeypatch, 'fragment_composed', fragment_id='batch', fragments=rows)
    original_replace = service._replace_rows

    def fail_after_batch(conn, table, user_id, replacement_rows):
        original_replace(conn, table, user_id, replacement_rows)
        if table == 'server_reward_fragment_batches':
            raise RuntimeError('injected publish failure')

    monkeypatch.setattr(service, '_replace_rows', fail_after_batch)
    with pytest.raises(RuntimeError, match='injected publish failure') as failure:
        service.build_and_publish(1, 'job', {"ok": True})
    service.fail_and_restore(1, 'job', failure.value, failed_stage='publish')
    with store._connect() as conn:
        assert conn.execute("SELECT id FROM server_reward_ledger WHERE id='old'").fetchone()[0] == 'old'
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragment_batches WHERE user_id=1").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragment_contributions WHERE user_id=1").fetchone()[0] == 0
        report = json.loads(conn.execute("SELECT failure_report_json FROM server_reward_rebuild_jobs WHERE id='job'").fetchone()[0])
    assert report['recovery']['verified'] is True
    assert report['causes'][0]['table'] == 'server_reward_fragment_batches'
    assert report['causes'][0]['check'] == 'projection_insert_failed'


@pytest.mark.parametrize("event_type,fragment_id,quantity,fragments,check", [
    ('fragment_expired', 'missing', 1, (), 'orphan_fragment_backpack_event'),
    ('fragment_composed', 'missing-batch', 1, (), 'invalid_composed_fragment_event'),
    ('fragment_composed', 'batch', 2, (_fragment_row('a', status='consumed', batch='batch'),), 'invalid_composed_fragment_event'),
    ('fragment_composed', 'batch', 0, (_fragment_row('a', status='consumed', batch='batch'),), 'invalid_composed_fragment_event'),
    ('fragment_future', 'frag', 1, (_fragment_row('frag'),), 'unknown_fragment_backpack_event'),
    ('fragment_expired', 'frag', 1, (_fragment_row('frag', reward_id='other', progress=15),), 'orphan_fragment_backpack_event'),
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


def test_expired_frozen_legacy_fragment_survives_real_rebuild(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-09-01')")
    reward_id = store.create_reward(
        1, "解锁手机", price=0, redemption_mode="task", fulfillment_mode="fragment",
        fragment_target_count=10, inventory_mode="monthly", inventory_limit=10,
    )
    legacy_id = "legacy-fragment-0d03dd"
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_reward_fragments(
            id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
            fragment_measure_mode,progress_units,consumed_units,issued_at,expires_at,status,
            created_at,updated_at) VALUES(?,1,?,'habit','deleted-habit','legacy:event',4,
            'count',15,14,'2026-09-07','2026-10-01','expired','2026-09-07','2026-10-01')""",
            (legacy_id, reward_id))
        conn.execute("""INSERT INTO server_backpack_events(
            id,user_id,ledger_id,event_type,reward_id,fragment_id,quantity,created_at)
            VALUES('legacy-event',1,'missing','fragment_expired',?,?,15,'2026-10-01')""",
            (reward_id, legacy_id))
        snapshot = {"ledger": [], "bindings": [], "fragments": [{"reward_id": reward_id}]}
        conn.execute("INSERT INTO server_habit_frozen_audit VALUES(1,'deleted-habit','binding',?,'2026-10-01')",
                     (json.dumps(snapshot),))
    service = RewardRebuildService(store)
    preview = service.preview(1, "2026-10-15")
    job, _ = service.start(1, "2026-10-15", preview["preview_hash"])
    assert service.build_and_publish(1, job["id"], {"ok": True})["balance"] == 0
    with store._connect() as conn:
        row = conn.execute("SELECT progress_units,consumed_units,status FROM server_reward_fragments WHERE id=?", (legacy_id,)).fetchone()
        assert tuple(row) == (15, 14, "expired")
        assert store.reward_wallet_service.list_backpack_fragments(1) == []


def test_active_multiunit_fragment_still_fails_and_restores(tmp_db_path, monkeypatch):
    fragment_id = "active-fragment-0d03dd"
    row = _fragment_row(fragment_id, status="active", progress=15)
    store, service = _case(tmp_db_path, monkeypatch, "fragment_acquired", fragment_id=fragment_id, fragments=(row,))
    with pytest.raises(RewardRebuildError) as failure:
        service.build_and_publish(1, "job", {"ok": True})
    assert str(failure.value) == "candidate_reference_invalid"
    assert failure.value.reward_rebuild_details == {"check": "noncanonical_fragment_unit", "record_id_suffix": "0d03dd"}
    report = service.fail_and_restore(1, "job", failure.value)
    assert report["recovery"]["status"] == "restored"
    assert report["recovery"]["verified"] is True


def test_unknown_fragment_status_is_rejected(tmp_db_path, monkeypatch):
    row = _fragment_row("unknown-status", status="future")
    store, service = _case(tmp_db_path, monkeypatch, "fragment_acquired",
                           fragment_id="unknown-status", fragments=(row,))
    with pytest.raises(RewardRebuildError) as failure:
        service.build_and_publish(1, "job", {"ok": True})
    assert failure.value.reward_rebuild_details["check"] == "unknown_fragment_status"


def test_real_rebuild_replaces_legacy_phone_projection_with_seven_count_fragments(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        for index in range(8):
            habit_id = f"h{index}"
            conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES(?,1,?,0,'local','2026-10-01','2026-10-01')", (habit_id, habit_id))
            conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'habit',?,0,0,'2026-10-01')", (habit_id,))
            conn.execute("INSERT INTO server_habit_checkins(id,user_id,habit_id,checkin_date,checkin_time,status,updated_at) VALUES(?,1,?,'2026-10-01','2026-10-01 08:00:00',2,'2026-10-01 08:00:00')", (f"c{index}", habit_id))
    reward_id = store.create_reward(1, "解锁手机", price=0, redemption_mode="task",
                                    fulfillment_mode="fragment", fragment_target_count=7,
                                    inventory_mode="monthly", inventory_limit=10)
    for index in range(8):
        store.bind_reward_source(1, reward_id, "habit", f"h{index}")
    with store._transact() as conn:
        conn.execute("UPDATE server_rewards SET fragment_measure_mode='percent' WHERE id=?", (reward_id,))
        conn.execute("UPDATE server_reward_source_bindings SET drop_mode='random',drop_min_units=10,drop_max_units=20 WHERE reward_id=?", (reward_id,))
    store.update_reward(1, reward_id, fragment_target_count=7)
    service = RewardRebuildService(store)
    preview = service.preview(1, "2026-10-01")
    job, created = service.start(1, "2026-10-01", preview["preview_hash"])
    assert created is True
    report = service.build_and_publish(1, job["id"], {"ok": True})
    assert not report["skipped"], report["skipped"]
    assert report["fragment_rows"] == 8, report
    with store._connect() as conn:
        fragments = conn.execute("SELECT fragment_measure_mode,progress_units,status FROM server_reward_fragments ORDER BY id").fetchall()
        assert all(tuple(row[:2]) == ("count", 1) for row in fragments)
        assert [row[2] for row in fragments].count("consumed") == 7
        assert [row[2] for row in fragments].count("active") == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?", (f"unlock:{reward_id}:fragment:%",)).fetchone()[0] == 1


def test_publish_replaces_old_composed_fragment_dependencies_atomically(tmp_db_path, monkeypatch):
    rows = (_fragment_row('new', status='consumed', batch='new-batch'),)
    store, service = _case(tmp_db_path, monkeypatch, 'fragment_composed',
                           fragment_id='new-batch', fragments=rows)
    with store._transact() as conn:
        old = _fragment_row('old-fragment', status='consumed', batch='old-batch')
        conn.execute("""INSERT INTO server_reward_fragments(
            id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
            fragment_measure_mode,progress_units,consumed_units,issued_at,expires_at,status,
            compose_batch_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", old)
        conn.execute("""INSERT INTO server_reward_fragment_batches VALUES
            ('old-batch-row',1,'old-batch','reward',1,'count',1,1,'old',
             '2026-08-25','exact','2026-08-25','2026-08-25')""")
        conn.execute("""INSERT INTO server_reward_fragment_contributions VALUES
            ('old-contribution',1,'old-batch','old-fragment',1,0,1,'2026-08-25')""")
    with store._connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
            conn.execute("DELETE FROM server_reward_fragments WHERE user_id=1")
    report = service.build_and_publish(1, 'job', {'ok': True})
    assert report['balance'] == 0
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragment_contributions WHERE user_id=1").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pragma_foreign_key_check").fetchone()[0] == 0
