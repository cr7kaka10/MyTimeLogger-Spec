# -*- coding: utf-8 -*-
import json
import sqlite3
from pathlib import Path

from server.models.server_schema import ensure_server_schema
from server.sync_sql_allowlist import SYNC_TABLES, primary_key_for, server_table_for


ROOT_DIR = Path(__file__).resolve().parents[2]


def test_shared_sync_entity_registry_matches_server_schema_and_allowlist(tmp_path):
    registry = json.loads((ROOT_DIR / "shared" / "protocol" / "sync-entities.json").read_text(encoding="utf-8"))
    entities = registry["entities"]
    client_tables = [entity["clientTable"] for entity in entities]
    assert len(client_tables) == len(set(client_tables))
    assert client_tables == list(SYNC_TABLES)
    by_table = {entity["clientTable"]: entity for entity in entities}
    fragments = by_table["reward_fragments"]
    assert fragments["serverTable"] == "server_reward_fragments"
    assert fragments["ownership"] == "server_owned"
    assert fragments["direction"] == "pull_only"
    assert fragments["outbox"] is False
    for table in ("management_plans", "management_plan_revisions"):
        assert by_table[table]["ownership"] == "server_owned"
        assert by_table[table]["direction"] == "pull_only"
        assert by_table[table]["outbox"] is False

    conn = sqlite3.connect(tmp_path / "registry_contract.db")
    ensure_server_schema(conn)
    for entity in entities:
        assert server_table_for(entity["clientTable"]) == entity["serverTable"]
        assert primary_key_for(entity["clientTable"]) == entity["primaryKey"]
        cols = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({entity['serverTable']})").fetchall()
        }
        assert entity["primaryKey"] in cols
        if entity["ownership"] == "server_owned":
            assert entity["direction"] == "pull_only"
            assert entity["outbox"] is False
    conn.close()
