import argparse
import hashlib
import json
import sqlite3


TABLES = ("server_tasks", "server_habits", "server_habit_checkins")


def audit_provider_mirror_ownership(db_path: str, target_date: str) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        users = [row[0] for row in conn.execute("SELECT id FROM users ORDER BY id")]
        counts = {
            str(user_id): {
                table: conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user_id,)
                ).fetchone()[0]
                for table in TABLES
            }
            for user_id in users
        }
        for user_id in users:
            counts[str(user_id)]["target_date_tasks"] = conn.execute(
                "SELECT COUNT(*) FROM server_tasks WHERE user_id=? AND substr(due_date,1,10)=? AND deleted_at IS NULL",
                (user_id, target_date),
            ).fetchone()[0]
        credentials = {}
        for row in conn.execute(
            "SELECT user_id,value FROM server_system_config WHERE key='ticktick_config' ORDER BY user_id"
        ):
            try:
                token = str(json.loads(row["value"] or "{}").get("access_token") or "")
            except (TypeError, ValueError):
                token = ""
            if token:
                digest = hashlib.sha256(token.encode()).hexdigest()[:12]
                credentials.setdefault(digest, []).append(row["user_id"])
        return {
            "target_date": target_date,
            "users": counts,
            "credential_fingerprints": [
                {"fingerprint": digest, "user_ids": owners, "shared": len(owners) > 1}
                for digest, owners in sorted(credentials.items())
            ],
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="只读审计 provider 镜像归属")
    parser.add_argument("db_path")
    parser.add_argument("--date", default="2026-09-06")
    args = parser.parse_args()
    print(json.dumps(audit_provider_mirror_ownership(args.db_path, args.date), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
