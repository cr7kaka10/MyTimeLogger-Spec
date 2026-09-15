# -*- coding: utf-8 -*-
"""报告输出目录解析。"""

import json
import os
from pathlib import Path


PROJECT_TMP_REPORTS_DIR = Path(__file__).resolve().parents[4] / "assets" / "tmp"


def _truthy(value):
    return str(value or "").lower() in ("1", "true", "yes")


def _config_reports_dir():
    skill_dir = Path(__file__).resolve().parents[1]
    config_path = skill_dir / "config.json"
    if not config_path.exists():
        return ""

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = json.load(file)
    except Exception:
        return ""

    candidates = [
        config.get("reports_dir"),
        config.get("report_output_dir"),
        (config.get("reports") or {}).get("dir") if isinstance(config.get("reports"), dict) else "",
        (config.get("output") or {}).get("reports_dir") if isinstance(config.get("output"), dict) else "",
    ]
    return next((str(item).strip() for item in candidates if str(item or "").strip()), "")


def resolve_reports_dir(output_dir=None, user_id=None):
    """返回报告输出目录，并确保目录存在。"""
    selected = (
        str(output_dir or "").strip()
        or os.getenv("MYTIMELOGGER_REPORTS_DIR", "").strip()
        or _config_reports_dir()
    )

    if not selected:
        selected = str(PROJECT_TMP_REPORTS_DIR)

    path = Path(selected).expanduser()
    if user_id is not None:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("invalid_report_user_id")
        path = path / f"user-{user_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path
