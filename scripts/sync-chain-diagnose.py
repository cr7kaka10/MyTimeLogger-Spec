# -*- coding: utf-8 -*-
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DB = ROOT / "desktop" / "local_data" / "my_time_logger.db"
SERVER_DB = ROOT / "server" / "data" / "mtl_server.db"


def rows(conn, sql, params=()):
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except sqlite3.Error as exc:
        return [{"error": str(exc)}]


def main():
    parser = argparse.ArgumentParser(description="输出任务或习惯的同步全链路状态")
    parser.add_argument("entity_id")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--reset-cursor", action="store_true")
    args = parser.parse_args()

    client = sqlite3.connect(CLIENT_DB)
    server = sqlite3.connect(SERVER_DB)
    client.row_factory = server.row_factory = sqlite3.Row
    if args.reset_cursor:
        client.execute("UPDATE client_sync_state SET value='0' WHERE key='last_server_version'")
        client.commit()

    result = {
        "entity_id": args.entity_id,
        "client_cursor": rows(client, "SELECT * FROM client_sync_state WHERE key='last_server_version'"),
        "client_tasks": rows(client, "SELECT * FROM tasks WHERE id=?", (args.entity_id,)),
        "client_habits": rows(client, "SELECT * FROM habits WHERE id=?", (args.entity_id,)),
        "client_checkins": rows(client, "SELECT * FROM habit_checkins WHERE habit_id=?", (args.entity_id,)),
        "client_outbox": rows(client, "SELECT * FROM sync_outbox WHERE record_id=? ORDER BY id DESC", (args.entity_id,)),
        "server_tasks": rows(server, "SELECT * FROM server_tasks WHERE user_id=? AND id=?", (args.user_id, args.entity_id)),
        "server_habits": rows(server, "SELECT * FROM server_habits WHERE user_id=? AND id=?", (args.user_id, args.entity_id)),
        "server_checkins": rows(server, "SELECT * FROM server_habit_checkins WHERE user_id=? AND habit_id=?", (args.user_id, args.entity_id)),
        "server_versions": rows(server, "SELECT * FROM server_change_log WHERE user_id=? AND (record_id=? OR entity_id=?) ORDER BY server_version DESC", (args.user_id, args.entity_id, args.entity_id)),
        "provider_sync": rows(server, "SELECT * FROM server_sync_state WHERE user_id=? AND system='ticktick'", (args.user_id,)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    client.close()
    server.close()


if __name__ == "__main__":
    main()
