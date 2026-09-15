# -*- coding: utf-8 -*-
"""
CategoryManager 单元测试（6 个用例）
"""
import pytest
from server.models.category_manager import CategoryManager


def test_init_creates_table(tmp_db_path):
    """初始化后 categories 表应存在"""
    import sqlite3
    cm = CategoryManager(db_path=tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='categories'")
    assert cursor.fetchone() is not None
    conn.close()


def test_add_category(tmp_db_path):
    """添加分类后应可查询到"""
    cm = CategoryManager(db_path=tmp_db_path)
    cm.add_category(name="测试分类", icon="📚", color="#5E81AC", group_name="输入")
    cats = cm.get_all_active()
    names = [c["name"] for c in cats]
    assert "测试分类" in names


def test_get_all_active(tmp_db_path):
    """get_all_active 应返回列表"""
    cm = CategoryManager(db_path=tmp_db_path)
    result = cm.get_all_active()
    assert isinstance(result, list)


def test_get_id_by_name(tmp_db_path):
    """按名称查 ID 应返回正整数"""
    cm = CategoryManager(db_path=tmp_db_path)
    cm.add_category(name="输入", icon="📖", color="#5E81AC", group_name="输入")
    cat_id = cm.get_id_by_name("输入")
    assert cat_id is not None
    assert isinstance(cat_id, int)
    assert cat_id > 0


def test_soft_delete(tmp_db_path):
    """软删除后 get_all_active 不应包含该分类"""
    cm = CategoryManager(db_path=tmp_db_path)
    cm.add_category(name="临时分类", icon="🗑️", color="#BF616A", group_name="其他")
    cats = cm.get_all_active()
    target = next((c for c in cats if c["name"] == "临时分类"), None)
    assert target is not None
    cm.remove_category(target["id"])
    cats_after = cm.get_all_active()
    names_after = [c["name"] for c in cats_after]
    assert "临时分类" not in names_after


def test_db_path_injection(tmp_db_path):
    """可通过 db_path 参数注入临时路径，不影响生产数据库"""
    cm = CategoryManager(db_path=tmp_db_path)
    cm.add_category(name="隔离测试", icon="🔒", color="#A3BE8C", group_name="测试")
    cats = cm.get_all_active()
    assert any(c["name"] == "隔离测试" for c in cats)
