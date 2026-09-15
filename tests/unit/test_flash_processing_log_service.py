import sqlite3

from server.domain.flash_processing_log_service import FlashProcessingLogService
from server.models.server_schema import ensure_server_schema


def test_flash_processing_logs_are_bounded_isolated_and_redacted_on_source_delete(tmp_path):
    path = tmp_path / "flash-logs.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.executemany("INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)", [(1, "u1", "x", "2026-08-11 10:00:00"), (2, "u2", "x", "2026-08-11 10:00:00")])
    conn.commit(); conn.close()

    def connect():
        result = sqlite3.connect(path); result.row_factory = sqlite3.Row
        return result

    service = FlashProcessingLogService(connect)
    deletion_log = service.start(1, "card-delete", "需要清理的输入", "提示词", "v1")
    service.finish(1, deletion_log, raw_output="{}", normalized={"ok": True})
    service.delete_for_card(1, "card-delete")
    with connect() as check:
        row = check.execute("SELECT input_text,prompt_snapshot,raw_output FROM server_flash_processing_logs WHERE flash_card_id='card-delete'").fetchone()
    assert tuple(row) == ("", "", None)
    for index in range(201):
        log_id = service.start(1, f"card-{index}", f"输入{index}", "提示词", "v1")
        service.finish(1, log_id, raw_output="{}", normalized={"ok": True})
    logs = service.list(1)
    assert len(logs) == 200
    assert service.list(2, "card-200") == []
