"""Account-isolated audit records for the flash insight pipeline."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from typing import Callable

from .management_plan_service import now_text


class FlashProcessingLogService:
    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self.connect = connect

    def start(self, user_id: int, card_id: str, input_text: str, prompt: str, version: str) -> str:
        log_id = str(uuid.uuid4())
        with closing(self.connect()) as conn:
            conn.execute("INSERT INTO server_flash_processing_logs(id,user_id,flash_card_id,input_text,prompt_snapshot,prompt_version,status,started_at) VALUES(?,?,?,?,?,?,?,?)", (log_id, user_id, card_id, input_text, prompt[:12000], version, "running", now_text()))
            conn.execute("DELETE FROM server_flash_processing_logs WHERE user_id=? AND id NOT IN (SELECT id FROM server_flash_processing_logs WHERE user_id=? AND deleted_at IS NULL ORDER BY started_at DESC LIMIT 200)", (user_id, user_id))
            conn.commit()
        return log_id

    def finish(self, user_id: int, log_id: str, *, raw_output: str | None = None, normalized: dict | None = None, error_code: str | None = None) -> None:
        with closing(self.connect()) as conn:
            conn.execute("UPDATE server_flash_processing_logs SET raw_output=?,normalized_output=?,status=?,error_code=?,completed_at=? WHERE id=? AND user_id=?", ((raw_output or "")[:12000] or None, json.dumps(normalized, ensure_ascii=False) if normalized is not None else None, "failed" if error_code else "done", error_code, now_text(), log_id, user_id))
            conn.commit()

    def list(self, user_id: int, card_id: str | None = None) -> list[dict]:
        with closing(self.connect()) as conn:
            query, params = "SELECT id,flash_card_id,input_text,prompt_snapshot,prompt_version,raw_output,normalized_output,status,error_code,started_at,completed_at FROM server_flash_processing_logs WHERE user_id=? AND deleted_at IS NULL", [user_id]
            if card_id: query += " AND flash_card_id=?"; params.append(card_id)
            return [dict(row) for row in conn.execute(query + " ORDER BY started_at DESC LIMIT 200", params)]

    def delete_for_card(self, user_id: int, card_id: str) -> None:
        with closing(self.connect()) as conn:
            conn.execute("UPDATE server_flash_processing_logs SET deleted_at=?,input_text='',prompt_snapshot='',raw_output=NULL,normalized_output=NULL WHERE user_id=? AND flash_card_id=?", (now_text(), user_id, card_id))
            conn.commit()
