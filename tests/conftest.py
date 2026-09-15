# -*- coding: utf-8 -*-
"""
pytest 全局 fixtures
"""
import pytest


@pytest.fixture
def tmp_db_path(tmp_path):
    """返回临时数据库路径，每个测试独立隔离。"""
    return str(tmp_path / "test.db")
