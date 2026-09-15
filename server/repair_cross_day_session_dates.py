"""Run a safe server session-date audit; add --apply to make the audited corrections."""

from __future__ import annotations

import argparse
import json

from server.domain.session_business_date_repair import repair_cross_day_session_dates
from server.store import ServerSleepStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit or repair cross-day server session business dates.")
    parser.add_argument("--db-path", required=True, help="Absolute path to the target server SQLite database.")
    parser.add_argument("--user-id", type=int, help="Limit audit/repair to one user.")
    parser.add_argument("--apply", action="store_true", help="Apply the audited corrections. Without this flag the command is read-only.")
    args = parser.parse_args()
    store = ServerSleepStore(args.db_path)
    findings = repair_cross_day_session_dates(store._connect, args.user_id, args.apply)
    print(json.dumps({"mode": "apply" if args.apply else "audit", "count": len(findings), "sessions": findings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
