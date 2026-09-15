import sqlite3

from server.domain.default_timer_categories import (
    DEFAULT_TIMER_CATEGORIES,
    DEFAULT_TIMER_CATEGORY_RECORDS,
    load_default_timer_categories,
)
from server.models.category_manager import CategoryManager, DEFAULT_CATEGORIES


EXPECTED_NAMES = [
    "输入", "输出", "副业生产", "副业营销", "副业研发", "工作", "吃饭", "带娃", "家务", "娱乐",
    "交通", "个人杂事", "休息", "活动", "运动", "松鼠病", "状态切换", "睡觉", "拉屎",
]


def test_shared_default_timer_categories_are_complete_and_stable():
    records = list(load_default_timer_categories())
    assert [item["name"] for item in records] == EXPECTED_NAMES
    assert [item["sort_order"] for item in records] == list(range(1, 20))
    assert len({item["name"] for item in records}) == 19
    assert len({item["key"] for item in records}) == 19
    assert tuple(records) == DEFAULT_TIMER_CATEGORY_RECORDS
    assert [row[0] for row in DEFAULT_TIMER_CATEGORIES] == EXPECTED_NAMES


def test_compatibility_category_manager_uses_shared_contract(tmp_path):
    db_path = tmp_path / "categories.db"
    manager = CategoryManager(str(db_path))
    assert [item["name"] for item in DEFAULT_CATEGORIES] == EXPECTED_NAMES
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name,sort_order FROM categories ORDER BY sort_order").fetchall()
    assert rows == list(zip(EXPECTED_NAMES, range(1, 20)))
    assert len(manager.get_all_active()) == 19
