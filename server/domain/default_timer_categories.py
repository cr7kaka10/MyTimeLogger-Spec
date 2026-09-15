from __future__ import annotations

import json
from pathlib import Path


CONTRACT_PATH = Path(__file__).parents[2] / "shared" / "protocol" / "default-timer-categories.json"


def load_default_timer_categories(path: Path = CONTRACT_PATH) -> tuple[dict, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(dict(item) for item in payload["categories"])


DEFAULT_TIMER_CATEGORY_RECORDS = load_default_timer_categories()
DEFAULT_TIMER_CATEGORIES = tuple(
    (item["name"], item["icon"], item["color"], item["group_name"], int(item["sort_order"]))
    for item in DEFAULT_TIMER_CATEGORY_RECORDS
)
