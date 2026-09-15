# -*- coding: utf-8 -*-
"""
模板加载器 (template_loader.py)
================================
负责从 assets/templates/ 目录加载 HTML 模板文件，并完成变量填充。

【设计原则】
- 不依赖 Jinja2 等外部模板引擎，使用 Python 标准库 str.format_map() 渲染
- 模板文件首次读取后缓存到模块级字典，避免重复磁盘 IO
- 使用 resource_path() 构建路径，确保 PyInstaller 打包后路径正确

【模板占位符格式】
- 使用单花括号：{variable_name}
- CSS 中的花括号需转义为双花括号：{{ 和 }}，否则 format_map 会报错

【使用示例】
    from server.utils.template_loader import render_template

    html = render_template('daily_card.html',
                           date_val='2024-01-15',
                           day_zh='星期一',
                           total_duration='120.0',
                           sessions_html='<div>...</div>')

【缓存机制】
    _template_cache 是模块级字典，key 为模板文件名，value 为文件内容字符串。
    首次调用 load_template(name) 时读取文件并写入缓存；
    后续调用直接从缓存返回，不再访问磁盘。
    缓存在进程生命周期内有效，重启程序后自动重建。
"""

import os
import logging

from server.utils.utils import resource_path

# 模块级模板缓存：{文件名: 模板内容字符串}
_template_cache: dict[str, str] = {}

# 模板文件所在目录（相对于项目根目录）
_TEMPLATES_DIR = os.path.join("assets", "templates")


def load_template(name: str) -> str:
    """
    加载指定名称的 HTML 模板文件内容。

    首次调用时从磁盘读取并写入内存缓存；后续调用直接返回缓存内容。

    Args:
        name: 模板文件名，如 'statistics_page.html'、'daily_card.html'

    Returns:
        模板文件的完整字符串内容

    Raises:
        FileNotFoundError: 模板文件不存在时抛出
        IOError: 文件读取失败时抛出
    """
    if name in _template_cache:
        return _template_cache[name]

    template_path = resource_path(os.path.join(_TEMPLATES_DIR, name))
    if not os.path.isfile(template_path):
        raise FileNotFoundError(
            f"模板文件未找到: {template_path}\n"
            f"请确认 assets/templates/{name} 存在，且 PyInstaller 打包时已包含该目录。"
        )

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        _template_cache[name] = content
        logging.debug(f"模板已加载并缓存: {name}")
        return content
    except IOError as e:
        raise IOError(f"读取模板文件失败: {template_path}, 原因: {e}") from e


def render_template(name: str, **kwargs) -> str:
    """
    加载模板并用关键字参数填充占位符，返回渲染后的 HTML 字符串。

    使用 str.format_map() 完成变量替换：
    - 模板中的 {variable} 会被替换为对应的 kwargs 值
    - 模板中的 CSS 花括号需写为 {{ 和 }}，渲染后自动还原为 { 和 }
    - 未在 kwargs 中提供的占位符会保持原样（使用 _SafeFormatMap 防止 KeyError）

    Args:
        name:   模板文件名，如 'daily_card.html'
        **kwargs: 占位符名称到值的映射，值会被转换为字符串

    Returns:
        填充完变量后的 HTML 字符串

    Raises:
        FileNotFoundError: 模板文件不存在时抛出（来自 load_template）
    """
    template = load_template(name)
    # 将所有值转为字符串，防止 format_map 因非字符串值报错
    str_kwargs = {k: str(v) for k, v in kwargs.items()}
    return template.format_map(_SafeFormatMap(str_kwargs))


class _SafeFormatMap(dict):
    """
    安全的 format_map 字典：对未提供的键返回原始占位符，而非抛出 KeyError。

    用途：防止模板中存在未传入的占位符时导致渲染失败。
    """

    def __missing__(self, key: str) -> str:
        logging.warning(f"模板占位符未提供值: {{{key}}}，保持原样")
        return f"{{{key}}}"
