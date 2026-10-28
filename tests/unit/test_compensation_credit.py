import uuid

import pytest

from server.store import COMPENSATION_DESCRIPTION, ServerSleepStore


@pytest.fixture
def account(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    assert store.create_user("compensation-isolated", "test-password")
    with store._connect() as conn:
        return store, conn.execute("SELECT id FROM users WHERE username='compensation-isolated'").fetchone()[0]


def test_compensation_template_is_unique_and_reserved(account):
    store, user_id = account
    first = [r for r in store.list_rewards(user_id) if r["redemption_mode"] == "compensation_credit"]
    second = [r for r in store.list_rewards(user_id) if r["redemption_mode"] == "compensation_credit"]
    assert len(first) == len(second) == 1
    assert first[0]["id"] == second[0]["id"]
    assert (first[0]["title"], first[0]["price"], first[0]["description"]) == (
        "补偿金币", 0, COMPENSATION_DESCRIPTION)
    with pytest.raises(ValueError, match="兑换类型无效"):
        store.create_reward(user_id, "伪补偿", redemption_mode="compensation_credit")
    with pytest.raises(ValueError, match="固定补偿商品"):
        store.update_reward(user_id, first[0]["id"], title="改名")
    with pytest.raises(ValueError, match="固定补偿商品"):
        store.delete_reward(user_id, first[0]["id"])


@pytest.mark.parametrize("amount,note,request_id", [
    (0, "面试", uuid.uuid4().hex), (-1, "面试", uuid.uuid4().hex),
    (1.234, "面试", uuid.uuid4().hex), (float("nan"), "面试", uuid.uuid4().hex),
    (2, "  ", uuid.uuid4().hex), (2, "面试", "bad-id"),
])
def test_compensation_rejects_invalid_input_without_ledger(account, amount, note, request_id):
    store, user_id = account
    reward_id = next(r["id"] for r in store.list_rewards(user_id) if r["redemption_mode"] == "compensation_credit")
    assert store.buy_reward(user_id, reward_id, amount, note, request_id)[0] is False
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=?", (user_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_backpack_events WHERE user_id=?", (user_id,)).fetchone()[0] == 0


def test_compensation_credit_is_idempotent_and_reason_visible(account):
    store, user_id = account
    reward_id = next(r["id"] for r in store.list_rewards(user_id) if r["redemption_mode"] == "compensation_credit")
    key = str(uuid.uuid4())
    assert store.buy_reward(user_id, reward_id, 200, "面试占用当天运动时间", key)[0]
    assert store.buy_reward(user_id, reward_id, 200, "面试占用当天运动时间", key)[0]
    assert store.buy_reward(user_id, reward_id, 201, "面试占用当天运动时间", key)[0] is False
    with store._connect() as conn:
        rows = conn.execute("SELECT amount,description,target_date FROM server_reward_ledger WHERE user_id=? AND source_type='store_compensation_credit'", (user_id,)).fetchall()
        assert len(rows) == 1 and rows[0]["amount"] == 200
        assert "面试占用当天运动时间" in rows[0]["description"] and rows[0]["target_date"]
        assert conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()[0] == 200
        assert conn.execute("SELECT COUNT(*) FROM server_backpack_events WHERE user_id=?", (user_id,)).fetchone()[0] == 0
