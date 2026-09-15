from server.domain.flash_skill_feedback_service import FlashSkillFeedbackService


def test_flash_feedback_schema_is_idempotent_and_has_private_indexes(tmp_path):
    from server.models.server_schema import ensure_server_schema
    import sqlite3

    conn = sqlite3.connect(tmp_path / "schema.db")
    ensure_server_schema(conn)
    ensure_server_schema(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"server_flash_polish_corrections", "server_flash_skill_change_events"} <= tables
    assert {"idx_flash_polish_correction_request", "idx_flash_polish_correction_card", "idx_flash_skill_events_history"} <= indexes
    assert conn.execute("SELECT COUNT(*) FROM server_flash_skill_change_events").fetchone()[0] == 0
    conn.close()


def test_candidates_are_account_isolated_and_only_activate_after_passing(tmp_path):
    from server.models.server_schema import ensure_server_schema
    import sqlite3

    path = tmp_path / "skill.db"
    def connect():
        conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; ensure_server_schema(conn); return conn
    with connect() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'a','x','2026-08-14'),(2,'b','x','2026-08-14')")
        conn.execute("INSERT INTO server_flash_cards(id,user_id,occurred_at,original_text,created_at,updated_at) VALUES('a',1,'2026-08-14','联系 a@example.com','x','x')")
        conn.execute("INSERT INTO server_flash_classification_feedback(user_id,flash_card_id,label,created_at,updated_at) VALUES(1,'a','todo','x','x')")
        conn.execute("INSERT INTO server_flash_polish_corrections(id,request_id,user_id,flash_card_id,original_text_snapshot,corrected_polished_text,created_at) VALUES('p1','r1',1,'a','联系 a@example.com 13800138000','联系 a@example.com。','2026-08-14 12:00:00')")
        conn.execute("INSERT INTO server_flash_polish_corrections(id,request_id,user_id,flash_card_id,original_text_snapshot,corrected_polished_text,created_at) VALUES('p2','r2',1,'a','联系 a@example.com 13800138000','联系 a@example.com！','2026-08-14 12:01:00')")
        conn.commit()
    service = FlashSkillFeedbackService(connect)
    samples = service.feedback_samples(1)
    assert samples == [
        {"kind": "polish", "input": "联系 [邮箱] [手机号]", "expected_output": "联系 [邮箱]！"},
        {"kind": "classification", "input": "联系 [邮箱]", "expected_label": "todo"},
    ]
    candidate = service.create_candidate(1, "# Flash Todo Diary Extraction Skill\nJSON", samples)
    assert service.evaluate_and_activate(1, candidate["id"], lambda _: (False, "bad"))["status"] == "failed"
    assert service.active_content(1) is None
    candidate = service.create_candidate(1, "# Flash Todo Diary Extraction Skill\nJSON v2", samples)
    assert service.evaluate_and_activate(1, candidate["id"], lambda _: (True, "passed"))["status"] == "active"
    assert service.active_content(1).endswith("v2")
    assert service.active_version(1) == candidate["version"]
    assert service.active_content(2) is None

    next_candidate = service.create_candidate(1, "# Flash Todo Diary Extraction Skill\nJSON v3\n保留语气", samples)
    assert next_candidate["parent_version"] == candidate["version"]
    history = service.history(1, limit=50)["events"]
    created = next(event for event in history if event["candidate_id"] == next_candidate["id"])
    assert created["rule_diff"]["added"] == ["保留语气"]
    assert created["sample_summary"] == {"classification": 1, "polish": 1}
    assert "联系" not in str(history)
    assert service.history(2)["events"] == []

    first_page = service.history(1, limit=2)
    second_page = service.history(1, cursor=first_page["next_cursor"], limit=2)
    assert {event["id"] for event in first_page["events"]}.isdisjoint(event["id"] for event in second_page["events"])


def test_skill_status_and_change_event_are_atomic(tmp_path):
    from server.models.server_schema import ensure_server_schema
    import sqlite3

    path = tmp_path / "skill-atomic.db"
    def connect():
        conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; ensure_server_schema(conn); return conn
    with connect() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'a','x','2026-08-14')")
        conn.commit()
    service = FlashSkillFeedbackService(connect)
    candidate = service.create_candidate(1, "# Flash Todo Diary Extraction Skill\nJSON")
    with connect() as conn:
        conn.execute("CREATE TRIGGER reject_skill_evaluation BEFORE INSERT ON server_flash_skill_change_events WHEN NEW.event_type='evaluated' BEGIN SELECT RAISE(ABORT,'event failed'); END")
        conn.commit()
    try:
        service.evaluate_and_activate(1, candidate["id"], lambda _: (True, "passed"))
        assert False, "event failure must abort activation"
    except sqlite3.IntegrityError:
        pass
    with connect() as conn:
        assert conn.execute("SELECT status FROM server_flash_skill_candidates WHERE id=?", (candidate["id"],)).fetchone()[0] == "pending"
        assert conn.execute("SELECT COUNT(*) FROM server_flash_skill_evaluations WHERE candidate_id=?", (candidate["id"],)).fetchone()[0] == 0
