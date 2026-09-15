# -*- coding: utf-8 -*-

import pytest

from server.provider_delta_filter import MissingProviderFingerprintError, classify_provider_records
from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema

import sqlite3


def test_task_same_etag_is_unchanged():
    result = classify_provider_records(
        [{"id": "task-1", "etag": "abc"}],
        {"task-1": {"source_etag": "abc", "status": 0}},
        "task",
    )

    assert result.stats()["unchanged"] == 1
    assert result.records_to_upsert() == []


def test_task_changed_etag_is_changed():
    result = classify_provider_records(
        [{"id": "task-1", "etag": "new"}],
        {"task-1": {"source_etag": "old", "status": 0}},
        "task",
    )

    assert [record["id"] for record in result.changed] == ["task-1"]


def test_missing_task_etag_raises_error_not_unchanged():
    with pytest.raises(MissingProviderFingerprintError) as exc_info:
        classify_provider_records(
            [{"id": "task-1", "title": "没有 etag"}],
            {"task-1": {"source_etag": "abc", "status": 0}},
            "task",
        )

    assert exc_info.value.record_type == "task"
    assert exc_info.value.record_key == "task-1"
    assert exc_info.value.field_name == "etag"


def test_missing_checkin_optime_raises_error():
    with pytest.raises(MissingProviderFingerprintError) as exc_info:
        classify_provider_records(
            [{"_provider_key": "habit-1:2026-06-14", "status": 2}],
            {},
            "habit_checkin",
        )

    assert exc_info.value.field_name == "opTime"


def test_checkin_same_optime_is_unchanged():
    result = classify_provider_records(
        [{"_provider_key": "habit-1:2026-06-14", "opTime": "1000"}],
        {"habit-1:2026-06-14": {"source_modified_time": "1000", "status": 2}},
        "habit_checkin",
    )

    assert result.stats()["unchanged"] == 1


def test_checkin_changed_optime_is_changed():
    result = classify_provider_records(
        [{"_provider_key": "habit-1:2026-06-14", "opTime": "2000"}],
        {"habit-1:2026-06-14": {"source_modified_time": "1000", "status": 2}},
        "habit_checkin",
    )

    assert result.changed[0]["_provider_key"] == "habit-1:2026-06-14"


def test_deleted_candidates_are_local_keys_missing_from_provider():
    result = classify_provider_records(
        [{"id": "task-1", "etag": "a"}],
        {
            "task-1": {"source_etag": "a"},
            "task-2": {"source_etag": "b"},
        },
        "task",
        include_deleted_candidates=True,
    )

    assert result.deleted_candidates == ["task-2"]


def test_db_provider_fingerprints_do_not_include_hash(tmp_path):
    db_path = tmp_path / "fingerprints.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-06-14 00:00:00')"
    )
    conn.execute(
        """INSERT INTO server_tasks
           (id, user_id, title, priority, status, raw_json, source_etag, source_modified_time, updated_at)
           VALUES ('task-1', 1, 't', 0, 0, '{}', 'etag-1', 'mtime-1', '2026-06-14 00:00:00')"""
    )
    conn.execute(
        """INSERT INTO server_habits
           (id, user_id, name, icon, is_active, raw_json, source_etag, source_modified_time, created_at, updated_at)
           VALUES ('habit-1', 1, 'h', 'x', 0, '{}', 'etag-h', 'mtime-h', '2026-06-14 00:00:00', '2026-06-14 00:00:00')"""
    )
    conn.execute(
        """INSERT INTO server_habit_checkins
           (id, user_id, habit_id, checkin_date, status, raw_json, source_modified_time, updated_at)
           VALUES ('ci-1', 1, 'habit-1', '2026-06-14', 2, '{}', 'op-1', '2026-06-14 00:00:00')"""
    )
    conn.commit()
    conn.close()

    db = ServerDBWrapper()
    db.log_path = str(db_path)

    tasks = db.get_provider_fingerprints(1, "server_tasks")
    habits = db.get_provider_fingerprints(1, "server_habits")
    checkins = db.get_provider_fingerprints(1, "server_habit_checkins")

    assert tasks["task-1"]["source_etag"] == "etag-1"
    assert habits["habit-1"]["source_etag"] == "etag-h"
    assert checkins["habit-1:2026-06-14"]["source_modified_time"] == "op-1"
    assert "source_hash" not in tasks["task-1"]
    assert "source_hash" not in habits["habit-1"]
    assert "source_hash" not in checkins["habit-1:2026-06-14"]
