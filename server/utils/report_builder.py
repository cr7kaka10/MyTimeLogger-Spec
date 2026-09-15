# -*- coding: utf-8 -*-
"""
报表构建模块 (report_builder.py)
================================
负责将数据库查询结果聚合并生成统计报表 HTML。

【职责划分】
- 本模块：数据聚合、Markdown 渲染、模板变量填充
- template_loader.py：HTML 模板文件的加载与缓存
- assets/templates/：HTML/CSS 模板文件（独立维护，不混入 Python 代码）
- gui.py：触发异步查询、接收结果、写文件、打开浏览器

【模板文件位置】
    assets/templates/
    ├── statistics_page.html      — 完整页面骨架（含 CSS）
    ├── daily_card.html           — 日期卡片片段
    ├── session_item_pomodoro.html — 专注类会话卡片
    └── session_item_lifestyle.html — 生活类会话卡片

【渲染机制】
    使用 template_loader.render_template(name, **kwargs) 完成变量填充。
    模板中的占位符格式为 {variable_name}，CSS 花括号转义为 {{ }}。
    模板文件首次读取后缓存到内存，避免重复磁盘 IO。

【设计原则】
- 所有函数均为纯函数（无副作用），便于单元测试
- 不依赖桌面 GUI 框架，可在非 GUI 环境下独立运行
- 中文注释说明业务逻辑，而非仅描述代码行为
"""

import re

from server.utils.template_loader import render_template


# ======================== Markdown 渲染 ========================

def render_markdown_lists(text: str) -> str:
    """
    将 Markdown 列表语法转换为 HTML 列表标签。

    支持的语法：
    - 无序列表：以 ``-``、``+``、``*`` 开头的行
    - 有序列表：以 ``1.``、``2.`` 等数字开头的行
    - 空行会关闭当前列表块

    Args:
        text: 原始 Markdown 文本，可能包含列表、普通段落或特殊值（"无"/"未填写总结"）

    Returns:
        转换后的 HTML 字符串；若输入为空或特殊值，原样返回。

    业务背景：
        专注总结和暂停原因均支持 Markdown 格式输入，
        在 HTML 报表中需要渲染为可读的列表结构。
    """
    # 特殊值直接返回，不做转换
    if not text or text == "无" or text == "未填写总结":
        return text

    lines = text.split('\n')
    result = []
    in_ul = False  # 当前是否在无序列表块中
    in_ol = False  # 当前是否在有序列表块中

    for line in lines:
        trimmed = line.strip()

        # 空行：关闭当前打开的列表块
        if not trimmed:
            if in_ul:
                result.append("</ul>")
                in_ul = False
            if in_ol:
                result.append("</ol>")
                in_ol = False
            continue

        # 匹配无序列表项（- / + / * 开头）
        ul_match = re.match(r'^[\-\+\*]\s+(.*)', trimmed)
        # 匹配有序列表项（数字. 开头）
        ol_match = re.match(r'^(\d+)\.\s+(.*)', trimmed)

        if ul_match:
            # 切换到无序列表：先关闭有序列表（如果有）
            if in_ol:
                result.append("</ol>")
                in_ol = False
            if not in_ul:
                result.append("<ul>")
                in_ul = True
            result.append(f"<li>{ul_match.group(1)}</li>")

        elif ol_match:
            # 切换到有序列表：先关闭无序列表（如果有）
            if in_ul:
                result.append("</ul>")
                in_ul = False
            if not in_ol:
                result.append("<ol>")
                in_ol = True
            result.append(f"<li>{ol_match.group(2)}</li>")

        else:
            # 普通段落：关闭所有列表块，作为普通文本输出
            if in_ul:
                result.append("</ul>")
                in_ul = False
            if in_ol:
                result.append("</ol>")
                in_ol = False
            result.append(trimmed + "<br>")

    # 文本结束时关闭未关闭的列表块
    if in_ul:
        result.append("</ul>")
    if in_ol:
        result.append("</ol>")

    return "".join(result)


# ======================== 会话卡片 HTML 生成 ========================

def build_session_item_html(row: tuple, cat_map: dict) -> str:
    """
    为单条专注记录生成 HTML 片段。

    根据分类的 group_name 区分两种展示风格：
    - 专注类（输入/输出分组）：显示完整的暂停明细和专注总结
    - 生活类（其他分组）：极简布局，只显示时间段和备注

    Args:
        row:     数据库查询返回的单行元组，字段顺序：
                 [0] start_time, [1] end_time, [2] duration,
                 [3] date, [4] weekday, [5] pause_count,
                 [6] pause_reasons, [7] summary, [8] category_id
        cat_map: 分类 ID → 分类信息字典的映射，用于查询分类名称和分组

    Returns:
        单条记录的 HTML 字符串（<div class="session-item">...</div>）

    业务背景：
        专注类记录（番茄钟模式）需要展示暂停原因和总结，
        生活类记录（如睡眠、运动）只需简洁展示时间和备注。
    """
    # 提取字段，兼容旧版本数据库（字段数量可能不足）
    # SELECT * 返回顺序：id(0), start_time(1), end_time(2), net_duration_minutes(3),
    # date(4), day_of_week(5), pause_count(6), pause_reasons(7), session_summary(8), category_id(9)
    start_time = row[1].split(' ')[-1] if ' ' in str(row[1]) else str(row[1])
    end_time = row[2].split(' ')[-1] if ' ' in str(row[2]) else str(row[2])
    duration = row[3]
    pause_count = row[6] if len(row) >= 9 else "0"
    pause_reasons_raw = row[7] if len(row) >= 9 else "无"
    summary = row[8] if len(row) >= 9 else "无记录"
    cat_id = row[9] if len(row) >= 10 else None

    # 查询分类信息，判断是否为专注类（番茄钟模式）
    cat_info = cat_map.get(cat_id, {})
    cat_name = cat_info.get("name", "")
    group_name = cat_info.get("group_name", "")
    # 按组名或名称判断：输入/输出分组属于专注类
    is_pomodoro = group_name in ["输入", "输出"] or cat_name in ["输入", "输出"]

    if is_pomodoro:
        # ---- 专注类：完整明细布局 ----
        # 处理暂停原因：支持 Markdown 列表和分号分隔两种格式
        reasons_html = ""
        if pause_reasons_raw and pause_reasons_raw != "无":
            if "\n" in pause_reasons_raw or any(
                pause_reasons_raw.startswith(s) for s in ["- ", "+ ", "* ", "1. "]
            ):
                # Markdown 格式：直接渲染为列表
                reasons_html = (
                    f"<div class='markdown-content' style='margin-top:2px; font-size:0.9em;'>"
                    f"{render_markdown_lists(pause_reasons_raw)}</div>"
                )
            else:
                # 分号分隔格式：渲染为标签气泡
                r_list = [r.strip() for r in pause_reasons_raw.split("; ") if r.strip()]
                reasons_tags_html = "".join(
                    [f"<span class='reason-tag'>{r}</span>" for r in r_list]
                )
                reasons_html = (
                    f"<div class='reason-tags' style='margin-top:6px;'>{reasons_tags_html}</div>"
                )
        else:
            reasons_html = "<span class='reason-tag-empty' style='margin-left:5px;'>无暂停记录</span>"

        return render_template(
            'session_item_pomodoro.html',
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            pause_count=pause_count,
            reasons_html=reasons_html,
            summary_html=render_markdown_lists(summary),
        )
    else:
        # ---- 生活类：极简布局 ----
        # 移除自动生成的"日常静默记录"前缀，只保留有意义的备注内容
        display_summary = summary
        if "日常静默记录" in summary:
            display_summary = summary.replace("日常静默记录", "").strip()

        remark_html = ""
        if display_summary:
            remark_html = f"<div class='card-remark'><strong>备注:</strong> {display_summary}</div>"

        # 如果摘要包含【】格式的任务标题，提取并单独展示
        task_label = summary.split('】')[0] + '】' if '】' in summary else ''

        return render_template(
            'session_item_lifestyle.html',
            start_time=start_time,
            end_time=end_time,
            task_label=task_label,
            duration=duration,
            remark_html=remark_html,
        )


# ======================== 日期卡片 HTML 生成 ========================

def build_daily_card_html(date_val: str, group_rows: list, cat_map: dict) -> str:
    """
    为某一天的所有专注记录生成日期卡片 HTML。

    卡片包含：
    - 卡片头部：日期、星期、当日总专注时长
    - 会话列表：当天每条记录的详情

    Args:
        date_val:   日期字符串，如 "2024-01-15"
        group_rows: 该日期下所有记录的行列表（已按时间排序）
        cat_map:    分类 ID → 分类信息字典的映射

    Returns:
        日期卡片的 HTML 字符串（<div class="card">...</div>）
    """
    # 星期中文映射
    week_map = {
        'Monday': '星期一', 'Tuesday': '星期二', 'Wednesday': '星期三',
        'Thursday': '星期四', 'Friday': '星期五', 'Saturday': '星期六', 'Sunday': '星期日'
    }

    # 获取星期名称（取第一行的 day_of_week 字段，index=5）
    day_zh = week_map.get(group_rows[0][5], str(group_rows[0][5]))

    # 计算当日总专注时长（累加所有记录的 net_duration_minutes 字段，index=3）
    total_duration = 0.0
    for r in group_rows:
        try:
            total_duration += float(r[3])
        except (ValueError, TypeError):
            pass  # 忽略无效的时长数据

    # 生成每条记录的 HTML
    sessions_html = ""
    for row in group_rows:
        sessions_html += build_session_item_html(row, cat_map)

    return render_template(
        'daily_card.html',
        date_val=date_val,
        day_zh=day_zh,
        total_duration=f"{total_duration:.1f}",
        sessions_html=sessions_html,
    )


# ======================== 数据聚合 ========================

def aggregate_rows_by_date(rows: list) -> dict:
    """
    将数据库查询结果按日期分组聚合。

    取最近 100 条记录，按日期倒序排列（最新日期在前），
    同一日期内保持原始顺序。

    Args:
        rows: 数据库查询返回的所有记录列表，每行为元组，
              row[3] 为日期字符串

    Returns:
        有序字典 {date_str: [row, ...]}，按日期倒序排列

    业务背景：
        报表只展示最近 100 条记录，避免页面过长影响浏览体验。
        日期倒序确保最新记录显示在最上方。
    """
    daily_groups: dict = {}
    # 取最近 100 条，reversed 使最新日期排在前面
    for row in reversed(rows[-100:]):
        if len(row) >= 5:
            date_val = row[4]  # date 列在 index=4（SELECT * 含 id）
            if date_val not in daily_groups:
                daily_groups[date_val] = []
            daily_groups[date_val].append(row)
    return daily_groups


# ======================== 完整报表生成 ========================

def build_report_html(rows: list, cat_map: dict) -> str:
    """
    将数据库查询结果和分类映射聚合为完整的统计报表 HTML 页面。

    这是本模块的主入口函数，gui.py 的 ``_on_stats_ready`` 回调应调用此函数。

    Args:
        rows:    数据库查询返回的所有专注记录，每行为元组
        cat_map: 分类 ID → 分类信息字典的映射，用于区分专注类和生活类

    Returns:
        完整的 HTML 页面字符串，可直接写入 .html 文件

    业务背景：
        报表以日期卡片形式展示专注历史，
        专注类记录显示暂停明细和总结，生活类记录极简展示。
    """
    # 按日期聚合数据
    daily_groups = aggregate_rows_by_date(rows)

    # 生成所有日期卡片的 HTML
    cards_html = ""
    for date_val, group_rows in daily_groups.items():
        cards_html += build_daily_card_html(date_val, group_rows, cat_map)

    # 无记录时显示引导提示
    content_html = (
        cards_html if cards_html
        else "<div class='empty'>暂无大专注学习记录，快去开启第一次沉浸式学习吧！</div>"
    )

    return build_stats_html_page(content_html)


def build_stats_html_page(content_html: str) -> str:
    """
    将内容 HTML 片段包装为完整的统计报表 HTML 页面。

    委托给 template_loader 加载 statistics_page.html 模板并填充内容。
    模板文件位于 assets/templates/statistics_page.html，包含完整 CSS 样式。

    Args:
        content_html: 已生成的卡片内容 HTML 片段

    Returns:
        完整的 HTML 页面字符串（含 DOCTYPE、head、body）

    业务背景：
        报表以静态 HTML 文件形式保存到本地，
        用户可通过浏览器查看，无需网络连接。
    """
    return render_template('statistics_page.html', content=content_html)
