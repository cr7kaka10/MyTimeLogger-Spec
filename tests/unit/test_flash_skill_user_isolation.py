import sqlite3

from server.domain.flash_skill_feedback_service import FlashSkillFeedbackService
from server.models.server_schema import ensure_server_schema


def test_evaluations_backfill_owner_and_reject_cross_account_candidate(tmp_path):
    path = tmp_path / "flash.db"
    def connect():
        conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; ensure_server_schema(conn); return conn
    with connect() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'alice','x','x'),(2,'bob','x','x')")
        conn.commit()
    service = FlashSkillFeedbackService(connect)
    candidate = service.create_candidate(1, "candidate")
    try:
        service.evaluate_and_activate(2, candidate["id"], lambda _: (True, "wrong account"))
        assert False, "another account must not evaluate this candidate"
    except LookupError:
        pass
    assert service.evaluate_and_activate(1, candidate["id"], lambda _: (True, "ok"))["status"] == "active"
    with connect() as conn:
        evaluation = conn.execute("SELECT user_id,candidate_id FROM server_flash_skill_evaluations").fetchone()
        assert dict(evaluation) == {"user_id": 1, "candidate_id": candidate["id"]}
