# -*- coding: utf-8 -*-
"""审计/调和“无可见报告却已评分”的睡眠快照；输出不含正文。"""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def audit(db_path: str) -> dict:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = conn.execute("""SELECT s.user_id,s.sleep_date FROM server_sleep_score_settlements s
          LEFT JOIN server_huawei_sleep_data d ON d.user_id=s.user_id AND d.date=s.sleep_date
          WHERE s.settlement_status='scored' AND (COALESCE(d.report_status,0)<1 OR
          (TRIM(COALESCE(d.analysis_report,''))='' AND TRIM(COALESCE(d.analysis_html,''))=''))
          ORDER BY s.user_id,s.sleep_date""").fetchall()
        sources = conn.execute("""SELECT l.source_type,COUNT(*) FROM server_reward_ledger l
          JOIN server_sleep_score_settlements s ON s.user_id=l.user_id AND s.sleep_date=l.target_date
          LEFT JOIN server_huawei_sleep_data d ON d.user_id=s.user_id AND d.date=s.sleep_date
          WHERE s.settlement_status='scored' AND (COALESCE(d.report_status,0)<1 OR
          (TRIM(COALESCE(d.analysis_report,''))='' AND TRIM(COALESCE(d.analysis_html,''))=''))
          AND l.source_type IN ('sleep_settlement_reward','sleep_cycle_penalty','sleep_completion_reward')
          GROUP BY l.source_type ORDER BY l.source_type""").fetchall()
    return {"candidates": len(rows), "by_user": {str(uid): sum(1 for row in rows if row[0] == uid) for uid in sorted({r[0] for r in rows})}, "ledger_types": dict(sources)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("db_path"); parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(); before = audit(args.db_path)
    result = {"before": before}
    if args.apply:
        from server.store import ServerSleepStore
        ServerSleepStore(args.db_path)  # 初始化流程在单事务调和后重建受影响账户钱包。
        result["reconciled"] = {"candidates": before["candidates"], "users": len(before["by_user"])}
        result["after"] = audit(args.db_path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
