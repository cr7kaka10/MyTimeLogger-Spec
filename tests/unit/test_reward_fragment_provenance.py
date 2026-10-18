import inspect
import sqlite3

import pytest

from server.store import ServerSleepStore
from server.domain.reward_candidate_builder import RewardCandidateBuilder
from server.domain.reward_fragment_provenance import RewardFragmentProvenance


def test_provenance_schema_is_idempotent_and_enforces_units_and_owner(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.executemany("INSERT INTO users VALUES (?,?,?,?)", ((1, "u1", "x", "2026-10-01"), (2, "u2", "x", "2026-10-01")))
    reward1 = store.create_reward(1, "r1", fulfillment_mode="fragment")
    reward2 = store.create_reward(2, "r2", fulfillment_mode="fragment")
    with store._transact() as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"server_reward_fragment_batches", "server_reward_fragment_contributions"} <= names
        conn.execute("""INSERT INTO server_reward_fragments
            (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
             progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
            VALUES ('foreign',2,?,'habit','h','event',1,1,0,'2026-10-01','2026-11-01','active','2026-10-01','2026-10-01')""", (reward2,))
        conn.execute("""INSERT INTO server_reward_fragment_batches VALUES
            ('batch:1:b',1,'b',?,1,'count',7,1,'ledger','2026-10-01','exact','2026-10-01','2026-10-01')""", (reward1,))
        for fragment_id, units in (("foreign", 1), ("missing", 0)):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""INSERT INTO server_reward_fragment_contributions VALUES
                    (?,?,?,?,?,?,?,?)""", (f"c:{fragment_id}", 1, "b", fragment_id, units, 0, units, "2026-10-01"))


def test_provenance_repository_is_idempotent_and_sums_units(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
    reward_id = store.create_reward(1, "r", fulfillment_mode="fragment")
    with store._transact() as conn:
        for index in range(7):
            conn.execute("""INSERT INTO server_reward_fragments
                (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
                 progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
                VALUES (?,1,?,'habit',?, ?,1,1,0,'2026-10-01','2026-11-01','active','2026-10-01','2026-10-01')""",
                (f"f{index}", reward_id, f"h{index}", f"e{index}"))
        args = (conn, 1, "batch", reward_id, 1, "count", 7, 1, "ledger", "2026-10-01")
        assert RewardFragmentProvenance.record_batch(*args) == RewardFragmentProvenance.record_batch(*args)
        contributions = [(f"f{index}", 0, 1) for index in range(7)]
        RewardFragmentProvenance.append_contributions(conn, 1, "batch", contributions, "2026-10-01")
        summary = RewardFragmentProvenance.append_contributions(conn, 1, "batch", contributions, "2026-10-01")
        assert summary["expected_units"] == summary["actual_units"] == 7
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragment_contributions").fetchone()[0] == 7


def _composed_store(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('h',1,'习惯',0,'local','2026-10-01','2026-10-01')")
    reward_id = store.create_reward(1, "卡片", redemption_mode="task", fulfillment_mode="fragment", fragment_target_count=2)
    store.bind_reward_source(1, reward_id, "habit", "h")
    with store._transact() as conn:
        for index in range(2):
            store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, "habit", "h", f"event:{index}", "习惯", "2026-10-01")
        batch_id = conn.execute("SELECT fragment_id FROM server_backpack_events WHERE event_type='fragment_composed'").fetchone()[0]
    return store, reward_id, batch_id


def test_unused_composed_output_is_split_when_one_fragment_is_revoked(tmp_db_path):
    store, _, _ = _composed_store(tmp_db_path)
    with store._transact() as conn:
        fragment_id = conn.execute("SELECT id FROM server_reward_fragments WHERE completion_event_key='event:0'").fetchone()[0]
        located = RewardFragmentProvenance.batch_for_fragment(conn, 1, fragment_id)
        assert located and len(located["contributions"]) == 2 and located["output_action"] is None
        store.reward_settlement_service.revoke_fragments_for_event_in_txn(conn, 1, "habit", "h", "event:0")
        states = dict(conn.execute("SELECT completion_event_key,status FROM server_reward_fragments"))
        assert states == {"event:0": "revoked", "event:1": "active"}
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 0


def test_unused_output_recomposes_from_remaining_current_period_units(tmp_db_path):
    store, reward_id, _ = _composed_store(tmp_db_path)
    store.update_reward(1, reward_id, inventory_mode="monthly", inventory_limit=1)
    with store._transact() as conn:
        for index in (2, 3):
            store.reward_settlement_service.grant_task_unlocks_in_txn(
                conn, 1, "habit", "h", f"event:{index}", "习惯", "2026-10-01",
            )
        store.reward_settlement_service.revoke_fragments_for_event_in_txn(
            conn, 1, "habit", "h", "event:0",
        )
        states = dict(conn.execute("SELECT completion_event_key,status FROM server_reward_fragments"))
        assert states["event:0"] == "revoked"
        assert list(states.values()).count("consumed") == 2
        assert list(states.values()).count("active") == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?", (f"unlock:{reward_id}:fragment:%",)).fetchone()[0] == 1


def test_used_composed_output_creates_one_debt_and_next_fragment_settles_it(tmp_db_path):
    store, reward_id, _ = _composed_store(tmp_db_path)
    with store._connect() as conn:
        output_id = conn.execute("SELECT id FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0]
    assert store.use_backpack_item(1, output_id)[0] is True
    for _ in range(2):
        with store._transact() as conn:
            store.reward_settlement_service.revoke_fragments_for_event_in_txn(conn, 1, "habit", "h", "event:0")
    with store._transact() as conn:
        assert tuple(conn.execute("SELECT COUNT(*),SUM(remaining_units) FROM server_reward_fragment_debts").fetchone()) == (1, 1)
        store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, "habit", "h", "event:2", "习惯", "2026-10-01")
        assert conn.execute("SELECT SUM(remaining_units) FROM server_reward_fragment_debts").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM server_reward_fragments WHERE completion_event_key='event:2'").fetchone()[0] == "revoked"
        store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, "habit", "h", "event:3", "习惯", "2026-10-01")
        assert conn.execute("SELECT status FROM server_reward_fragments WHERE completion_event_key='event:3'").fetchone()[0] == "active"
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?", (f"unlock:{reward_id}:fragment:%",)).fetchone()[0] == 1


def test_migration_normalizes_only_active_unconsumed_count_fragments(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
    reward_id = store.create_reward(1, "卡片", fulfillment_mode="fragment", fragment_target_count=7)
    with store._transact() as conn:
        for fragment_id, status, consumed, expires in (("active", "active", 0, "2026-11-01"), ("old", "expired", 0, "2026-10-01")):
            conn.execute("""INSERT INTO server_reward_fragments
                (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
                 progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
                VALUES (?,1,?,'habit',?,?,1,15,?,'2026-09-01',?,?, '2026-09-01','2026-09-01')""",
                (fragment_id, reward_id, fragment_id, fragment_id, consumed, expires, status))
    ServerSleepStore(db_path=tmp_db_path)
    with store._connect() as conn:
        assert dict(conn.execute("SELECT id,progress_units FROM server_reward_fragments").fetchall()) == {"active": 1, "old": 15}
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 0


def test_migration_backfills_exact_then_legacy_without_changing_assets(tmp_db_path):
    store, _, batch_id = _composed_store(tmp_db_path)
    with store._transact() as conn:
        conn.execute("DELETE FROM server_reward_fragment_contributions")
        conn.execute("DELETE FROM server_reward_fragment_batches")
        RewardFragmentProvenance.migrate_user(conn, 1, "2026-10-02")
        assert RewardFragmentProvenance.summary(conn, 1, batch_id)["actual_units"] == 2
        conn.execute("DELETE FROM server_reward_fragment_contributions")
        conn.execute("DELETE FROM server_reward_fragment_batches")
        conn.execute("UPDATE server_reward_fragments SET status='expired',compose_batch_id=NULL")
        before = tuple(conn.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM server_reward_ledger").fetchone())
        RewardFragmentProvenance.migrate_user(conn, 1, "2026-10-02")
        batch = conn.execute("SELECT provenance_kind FROM server_reward_fragment_batches WHERE batch_id=?", (batch_id,)).fetchone()
        assert batch[0] == "legacy_attested"
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragment_contributions").fetchone()[0] == 0
        assert tuple(conn.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM server_reward_ledger").fetchone()) == before
        conn.execute("DELETE FROM server_reward_fragment_batches")
        conn.execute("DELETE FROM server_reward_ledger WHERE source_type='reward_buy'")
        RewardFragmentProvenance.migrate_user(conn, 1, "2026-10-02")
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragment_batches").fetchone()[0] == 0


def test_candidate_rebuild_recreates_provenance_after_expiry_before_wallet():
    source = inspect.getsource(RewardCandidateBuilder.build)
    expiry = source.index("expire_fragments_for_user_in_txn")
    provenance = source.index("RewardFragmentProvenance.migrate_user")
    wallet = source.index("rebuild_wallet_snapshot_in_txn")
    assert expiry < provenance < wallet
