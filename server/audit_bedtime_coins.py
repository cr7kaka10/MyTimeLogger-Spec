# -*- coding: utf-8 -*-
"""审计并显式撤销已废弃的旧 noon 入睡处罚。"""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import ServerSleepStore, resolve_server_db_path


def audit_read_only(db_path: str) -> dict:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT ledger.user_id,COUNT(*) AS ledger_count,COALESCE(SUM(ledger.amount),0) AS amount
               FROM server_reward_ledger AS ledger
               JOIN server_sleep_score_settlements AS settlement
                 ON settlement.user_id=ledger.user_id AND settlement.sleep_date=ledger.target_date
               WHERE ledger.source_type='sleep_bedtime_adjustment'
                 AND ledger.id LIKE 'sleep-bedtime-adjustment:%'
                 AND settlement.bedtime_coin_reason='截至北京时间12:00仍无有效睡眠记录'
               GROUP BY ledger.user_id ORDER BY ledger.user_id""",
        ).fetchall()
    return {"rule_version": "bedtime-coin-v1", "users": [
        {"user_id": row[0], "ledger_count": row[1], "amount": row[2]} for row in rows
    ]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", nargs="?", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db_path = resolve_server_db_path(args.db_path)
    result = ServerSleepStore(db_path).sleep_reward_service.rollback_bedtime_coins() if args.apply else audit_read_only(db_path)
    print(json.dumps({"mode": "rollback" if args.apply else "audit", **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
