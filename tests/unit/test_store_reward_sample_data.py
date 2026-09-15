import sqlite3
import asyncio

from server.db_wrapper import ServerDBWrapper
from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


def _user_with_categories(db_path, email):
    store = ServerSleepStore(db_path)
    assert store.create_user(email, "password")
    user_id = store.verify_user(email, "password")
    service = SampleDataInitializationService(db_path)
    assert not service.ensure_user_sample_data(user_id)
    return user_id, service


def _add_habits(db_path, user_id, rows=(("brush", "刷牙"), ("face", "洗脸"))):
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO server_habits (id, user_id, name, is_active, created_at, updated_at) VALUES (?, ?, ?, 0, '2026-08-04 00:00:00', '2026-08-04 00:00:00')",
            [(f"{user_id}:{key}", user_id, name) for key, name in rows],
        )


def test_store_reward_defaults_are_once_per_account_and_synced(tmp_db_path):
    first, service = _user_with_categories(tmp_db_path, "first@example.com")
    second, _ = _user_with_categories(tmp_db_path, "second@example.com")
    _add_habits(tmp_db_path, first); _add_habits(tmp_db_path, second)
    assert service.ensure_user_sample_data(first)
    assert not service.ensure_user_sample_data(first)
    assert service.ensure_user_sample_data(second)
    with sqlite3.connect(tmp_db_path) as conn:
        rewards = conn.execute("SELECT title,unlock_source_type,unlock_required_count,inventory_mode,inventory_limit FROM server_rewards WHERE user_id=? AND is_active=1 ORDER BY id", (first,)).fetchall()
        phone_bindings = conn.execute("SELECT h.name,b.drop_mode,b.drop_min_units,b.drop_max_units FROM server_reward_source_bindings b JOIN server_habits h ON h.id=b.source_id AND h.user_id=b.user_id WHERE b.user_id=? AND b.reward_id=? ORDER BY h.name", (first, f"{first}:seed:reward:phone")).fetchall()
        archived_phones = conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=? AND id IN (?,?) AND is_active=0", (first, f"{first}:seed:reward:phone-brush", f"{first}:seed:reward:phone-face")).fetchone()[0]
        goals = conn.execute("SELECT title, metric, target_value, period, reward_coins, penalty_coins FROM server_goals WHERE user_id=? ORDER BY id", (first,)).fetchall()
        bindings = conn.execute("SELECT COUNT(*) FROM server_goal_category_bindings WHERE user_id=?", (first,)).fetchone()[0]
        changes = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND table_name IN ('server_goals', 'server_goal_category_bindings', 'server_rewards')", (first,)).fetchone()[0]
        second_rewards = conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=?", (second,)).fetchone()[0]
    assert rewards == [("出去玩一天", "goal", 1, "unlimited", None), ("来一发", "goal", 1, "unlimited", None), ("解锁手机", None, 1, "monthly", 10)]
    assert [tuple(row) for row in phone_bindings] == [("刷牙", "random", 10, 20), ("洗脸", "random", 10, 20)]
    assert archived_phones == 2
    assert [tuple(goal) for goal in goals] == [
        ("【天】输入+输出 ≥ 4.5h", "duration", 270.0, "daily", 20.0, 1.0),
        ("【周】输入+输出 ≥ 25h", "duration", 1500.0, "weekly", 100.0, 5.0),
        ("【天】副业≥1.5h", "duration", 90.0, "daily", 20.0, 5.0),
    ]
    assert bindings == 7 and changes >= 14 and second_rewards == 5
    synced = asyncio.run(SyncHub(ServerDBWrapper(tmp_db_path)).handle_pull_by_version(0, user_id=first))
    assert len(synced["tables"]["goals"]) == 3 and len(synced["tables"]["rewards"]) == 5


def test_phone_migration_binds_ad_habit_and_preserves_legacy_history(tmp_db_path):
    user_id, service = _user_with_categories(tmp_db_path, "phone-migration@example.com")
    _add_habits(tmp_db_path, user_id, (("brush", "刷牙"), ("face", "洗脸"), ("ad", "发广告帖")))
    assert service.ensure_user_sample_data(user_id)
    legacy_id = f"{user_id}:seed:reward:phone-brush"
    with sqlite3.connect(tmp_db_path) as conn:
        conn.execute("INSERT INTO server_reward_ledger(id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at) VALUES('legacy-phone-history',?,0,'reward_buy',?,'旧手机卡','2026-09-05','2026-09-05','2026-09-05')", (user_id, f"unlock:{legacy_id}:habit:old"))
    assert not service.ensure_user_sample_data(user_id)
    with sqlite3.connect(tmp_db_path) as conn:
        names = [row[0] for row in conn.execute("SELECT h.name FROM server_reward_source_bindings b JOIN server_habits h ON h.id=b.source_id WHERE b.reward_id=? ORDER BY h.name", (f"{user_id}:seed:reward:phone",))]
        history = conn.execute("SELECT source_id FROM server_reward_ledger WHERE id='legacy-phone-history'").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=? AND is_active=1 AND title LIKE '解锁手机%'", (user_id,)).fetchone()[0]
    assert names == ["刷牙", "发广告帖", "洗脸"]
    assert history == f"unlock:{legacy_id}:habit:old"
    assert active == 1


def test_exercise_scoring_migration_removes_arrival_sports_park_and_publishes_delete(tmp_db_path):
    user_id, service = _user_with_categories(tmp_db_path, "exercise_migration@example.com")
    with sqlite3.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO server_exercise_plan_schedule_items "
            "(id,user_id,plan_version,schedule_type,sort_order,time,item,note,accent,created_at,updated_at) "
            "VALUES ('legacy-arrival-park',?,'v1','weekday',99,'17:30','🚶 到达体育公园','','default','2026-08-26','2026-08-26')",
            (user_id,),
        )
    service.ensure_user_sample_data(user_id)
    with sqlite3.connect(tmp_db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM server_exercise_plan_schedule_items WHERE user_id=? AND item='到达体育公园'",
            (user_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND change_id=?",
            (user_id, f"seed:{user_id}:legacy-arrival-park:delete"),
        ).fetchone()[0] == 1
