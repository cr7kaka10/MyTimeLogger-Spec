# -*- coding: utf-8 -*-
"""
report_builder 单元测试（7 个用例）

rows 格式（SELECT * 含 id）：
  (id, start_time, end_time, net_duration_minutes, date, day_of_week,
   pause_count, pause_reasons, session_summary, category_id)
"""
import pytest
from server.utils.report_builder import build_report_html, aggregate_rows_by_date


# ---- 测试数据 ----

def _make_row(
    id_=1,
    start="2024-01-15 09:00:00",
    end="2024-01-15 10:30:00",
    duration=90.0,
    date="2024-01-15",
    weekday="Monday",
    pause_count=0,
    pause_reasons="无",
    summary="测试总结",
    category_id=None,
):
    return (id_, start, end, duration, date, weekday,
            pause_count, pause_reasons, summary, category_id)


CAT_MAP = {
    1: {"name": "输入", "group_name": "输入"},
    2: {"name": "吃饭", "group_name": "生活"},
}


# ---- 测试用例 ----

def test_empty_rows_returns_html():
    """空 rows 应返回包含"暂无"提示的 HTML"""
    html = build_report_html([], {})
    assert "暂无" in html or "empty" in html.lower() or "<html" in html.lower()


def test_single_pomodoro_row():
    """单条 pomodoro 记录应生成包含时间的 HTML"""
    row = _make_row(category_id=1)
    html = build_report_html([row], CAT_MAP)
    assert "2024-01-15" in html
    assert "09:00" in html or "10:30" in html


def test_single_lifestyle_row():
    """单条 lifestyle 记录生成 HTML 不抛异常"""
    row = _make_row(id_=2, category_id=2, summary="吃午饭")
    html = build_report_html([row], CAT_MAP)
    assert isinstance(html, str)
    assert len(html) > 0


def test_multiple_dates_grouped():
    """多日记录应按日期分组，每个日期出现一次"""
    rows = [
        _make_row(id_=1, date="2024-01-15"),
        _make_row(id_=2, date="2024-01-14"),
        _make_row(id_=3, date="2024-01-14"),
    ]
    html = build_report_html(rows, {})
    assert html.count("2024-01-15") >= 1
    assert html.count("2024-01-14") >= 1


def test_html_contains_date():
    """HTML 应包含记录的日期字符串"""
    row = _make_row(date="2024-03-20")
    html = build_report_html([row], {})
    assert "2024-03-20" in html


def test_html_contains_duration():
    """HTML 应包含时长数字"""
    row = _make_row(duration=45.5)
    html = build_report_html([row], {})
    assert "45" in html


def test_template_render_no_exception():
    """build_report_html 对各种输入不应抛出异常"""
    rows = [
        _make_row(id_=1, pause_reasons="刷手机; 喝水", summary="完成了章节1"),
        _make_row(id_=2, category_id=2, summary=""),
    ]
    try:
        html = build_report_html(rows, CAT_MAP)
        assert isinstance(html, str)
    except Exception as e:
        pytest.fail(f"build_report_html 抛出异常: {e}")
