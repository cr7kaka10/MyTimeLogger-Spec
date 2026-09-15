# -*- coding: utf-8 -*-
import pytest

from server.store import ServerSleepStore
from server.sync_sql_allowlist import primary_key_for, server_table_for


def test_allowlist_resolves_known_sync_table_identifiers():
    assert server_table_for("tasks") == "server_tasks"
    assert primary_key_for("external_rewards") == "ext_id"
    assert primary_key_for("system_config") == "key"


def test_allowlist_rejects_malicious_table_name():
    with pytest.raises(ValueError):
        server_table_for("tasks; DROP TABLE users;--")


def test_legacy_batch_push_rejects_unknown_table_before_sql(tmp_path):
    store = ServerSleepStore(str(tmp_path / "server.db"))
    result = store.batch_push(1, [{
        "table": "tasks; DROP TABLE users;--",
        "records": [{"id": "bad", "updated_at": "2026-07-04 22:00:00"}],
    }])

    assert result["accepted"] == 0
    assert result["rejected"] == 1
