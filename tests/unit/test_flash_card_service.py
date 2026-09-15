import sqlite3

import pytest

from server.domain.flash_card_service import FlashCardError, FlashCardService
from server.models.server_schema import ensure_server_schema


def _service(tmp_path):
    path = tmp_path / "flash-cards.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('u1','x','2026-08-09 12:00:00')")
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('u2','x','2026-08-09 12:00:00')")
    conn.commit(); conn.close()
    changes = []
    def connect():
        result = sqlite3.connect(path); result.row_factory = sqlite3.Row
        return result
    def record(conn, user_id, table, record_id, operation, fields):
        changes.append((user_id, table, record_id, operation, fields))
    return FlashCardService(connect, record), changes


def test_flash_card_crud_is_account_isolated_and_records_sync_change(tmp_path):
    service, changes = _service(tmp_path)
    created = service.create(1, {"original_text": "嗯，我觉得应该把阅读安排一下", "occurred_at": "2026-08-09 21:30:00"})

    assert created["original_text"] == "嗯，我觉得应该把阅读安排一下"
    assert service.list(1, "2026-08-09")[0]["id"] == created["id"]
    assert service.list(2) == []
    updated = service.update(1, created["id"], {"original_text": "安排阅读"})
    assert updated["original_text"] == "安排阅读"
    service.delete(1, created["id"])
    assert service.list(1) == []
    assert [change[3] for change in changes] == ["upsert", "upsert", "delete"]


def test_flash_card_rejects_cross_account_update(tmp_path):
    service, _ = _service(tmp_path)
    created = service.create(1, {"original_text": "闪念"})
    with pytest.raises(FlashCardError, match="闪念卡片不存在"):
        service.update(2, created["id"], {"original_text": "越权"})


def test_flash_card_polish_preserves_original_and_records_sync_change(tmp_path):
    service, changes = _service(tmp_path)
    created = service.create(1, {"original_text": "嗯嗯，我觉得，今天把阅读安排一下吧", "occurred_at": "2026-08-09 21:30:00"})

    polished = service.polish(1, created["id"], lambda _: "嗯，我觉得，今天把阅读安排一下吧。")

    assert polished["original_text"] == "嗯嗯，我觉得，今天把阅读安排一下吧"
    assert polished["polished_text"] == "嗯，我觉得，今天把阅读安排一下吧。"
    assert service.polish(1, created["id"], lambda _: "今天必须立刻完成阅读计划，绝不能拖延。 ")["polished_text"] == created["original_text"]
    assert changes[-1][3] == "upsert"
    with pytest.raises(FlashCardError, match="闪念卡片不存在"):
        service.polish(2, created["id"], lambda _: "越权")


def test_human_polish_correction_is_idempotent_versioned_and_account_isolated(tmp_path):
    service, changes = _service(tmp_path)
    created = service.create(1, {"original_text": "原文语气别改", "occurred_at": "2026-08-14 15:45:00"})
    before_status = created["analysis_status"]

    first = service.correct_polish(1, created["id"], {"request_id": "req-1", "corrected_text": "原文语气别改！"}, "skill-v8")
    retried = service.correct_polish(1, created["id"], {"request_id": "req-1", "corrected_text": "原文语气别改！"}, "skill-v8")
    second = service.correct_polish(1, created["id"], {"request_id": "req-2", "corrected_text": "只整理标点。"}, "skill-v8")

    assert first["original_text"] == "原文语气别改"
    assert retried["polished_text"] == "原文语气别改！"
    assert second["polished_text"] == "只整理标点。"
    assert second["analysis_status"] == before_status
    with service.connect() as conn:
        rows = {row["request_id"]: row for row in conn.execute("SELECT * FROM server_flash_polish_corrections WHERE user_id=1")}
    assert set(rows) == {"req-1", "req-2"}
    assert rows["req-1"]["original_text_snapshot"] == "原文语气别改"
    assert rows["req-2"]["previous_polished_text"] == "原文语气别改！"
    assert changes[-1][4]["human_polished"] is True
    with pytest.raises(FlashCardError) as foreign:
        service.correct_polish(2, created["id"], {"request_id": "req-3", "corrected_text": "越权"})
    assert foreign.value.status == 404


def test_human_polish_correction_validates_and_rolls_back_atomically(tmp_path):
    service, _ = _service(tmp_path)
    created = service.create(1, {"original_text": "绝不能覆盖"})
    with pytest.raises(FlashCardError):
        service.correct_polish(1, created["id"], {"request_id": "req-empty", "corrected_text": " "})
    with pytest.raises(FlashCardError):
        service.correct_polish(1, created["id"], {"request_id": "req-long", "corrected_text": "字" * 4001})
    service.record_change = lambda *_: (_ for _ in ()).throw(RuntimeError("sync write failed"))
    with pytest.raises(RuntimeError, match="sync write failed"):
        service.correct_polish(1, created["id"], {"request_id": "req-rollback", "corrected_text": "不能半成功"})
    assert service.get(1, created["id"])["polished_text"] is None
    with service.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_flash_polish_corrections").fetchone()[0] == 0


def test_delete_flash_card_removes_only_its_polish_corrections(tmp_path):
    service, _ = _service(tmp_path)
    deleted = service.create(1, {"original_text": "删除我"})
    kept = service.create(1, {"original_text": "保留我"})
    service.correct_polish(1, deleted["id"], {"request_id": "delete-1", "corrected_text": "删除我。"})
    service.correct_polish(1, kept["id"], {"request_id": "keep-1", "corrected_text": "保留我。"})
    service.delete(1, deleted["id"])
    with service.connect() as conn:
        rows = conn.execute("SELECT flash_card_id FROM server_flash_polish_corrections").fetchall()
    assert [row["flash_card_id"] for row in rows] == [kept["id"]]


def test_analysis_and_classification_feedback_never_overwrite_human_polish(tmp_path):
    service, _ = _service(tmp_path)
    card = service.create(1, {"original_text": "原文就这样！"})
    service.correct_polish(1, card["id"], {"request_id": "human-1", "corrected_text": "我确认的版本！"})

    analyzed = service.save_insights(1, card["id"], "模型初次改写。", {"mood": "愤怒", "content": "模型概括。"}, [])
    assert analyzed["polished_text"] == "我确认的版本！"
    run = service.record_classification_feedback(1, card["id"], "mood")
    reanalyzed = service.save_feedback_reanalysis(1, card["id"], run["run_id"], "模型再次改写。", {"mood": "愤怒", "content": "模型再次概括。"}, [])
    assert reanalyzed["polished_text"] == "我确认的版本！"
    assert reanalyzed["original_text"] == "原文就这样！"


def test_flash_card_insights_persist_diary_without_overwriting_source(tmp_path):
    service, changes = _service(tmp_path)
    created = service.create(1, {"original_text": "今天解决难题了，虽然累但很踏实"})

    updated = service.save_insights(1, created["id"], "今天解决了难题。虽然累，但很踏实。", {"mood": "踏实", "content": "我今天解决了难题，虽然疲惫，但感到踏实。"})

    assert updated["original_text"] == "今天解决难题了，虽然累但很踏实"
    assert updated["polished_text"] == "今天解决了难题。虽然累，但很踏实。"
    assert updated["diary_mood"] == "踏实"
    assert updated["diary_content"] == "我今天解决了难题，虽然疲惫，但感到踏实。"
    assert changes[-1][4]["has_diary"] is True
    with pytest.raises(FlashCardError, match="闪念卡片不存在"):
        service.save_insights(2, created["id"], "越权", None)


def test_flash_single_action_creates_one_local_task_and_complex_action_waits(tmp_path):
    service, changes = _service(tmp_path)
    direct = service.create(1, {"original_text": "给客户发邮件"})
    service.save_insights(1, direct["id"], "给客户发邮件。", None, [{"title": "给客户发邮件", "reason": "单一明确动作"}])
    service.save_insights(1, direct["id"], "给客户发邮件。", None, [{"title": "给客户发邮件", "reason": "重放"}])
    complex_card = service.create(1, {"original_text": "计划周末出行，然后订票并安排住宿"})
    service.save_insights(1, complex_card["id"], "计划周末出行，然后订票并安排住宿。", None, [{"title": "规划周末出行", "reason": "需要拆解"}])

    direct_rec = service.list_recommendations(1, [direct["id"]])[0]
    complex_rec = service.list_recommendations(1, [complex_card["id"]])[0]
    with service.connect() as conn:
        tasks = conn.execute("SELECT id,title,source FROM server_tasks WHERE user_id=1 AND source='local'").fetchall()
    assert direct_rec["status"] == "added" and direct_rec["creation_mode"] == "direct"
    assert len(tasks) == 1 and tasks[0]["title"] == "给客户发邮件"
    assert complex_rec["status"] == "pending" and complex_rec["creation_mode"] == "confirm"
    assert not any(change[1] == "server_tasks" and change[2] != tasks[0]["id"] for change in changes)


def test_flash_card_polish_failure_does_not_overwrite_card_and_analysis_only_links_draft(tmp_path):
    service, _ = _service(tmp_path)
    created = service.create(1, {"original_text": "记录一个想法"})

    with pytest.raises(FlashCardError, match="AI 润色失败"):
        service.polish(1, created["id"], lambda _: (_ for _ in ()).throw(RuntimeError("model down")))
    assert service.get(1, created["id"])["polished_text"] is None

    linked = service.mark_analysis_draft(1, created["id"], "draft-1")
    assert linked["analysis_status"] == "draft_ready"
    assert linked["analysis_draft_id"] == "draft-1"
    assert linked["original_text"] == "记录一个想法"


def test_flash_card_create_and_polish_keeps_original_on_success_or_failure(tmp_path):
    service, changes = _service(tmp_path)

    polished = service.create_and_polish(1, {"original_text": "嗯，今天把报告写一下吧"}, lambda: lambda _: "嗯，今天把报告写一下吧。")
    assert polished["polish_status"] == "done"
    assert polished["card"]["original_text"] == "嗯，今天把报告写一下吧"
    assert polished["card"]["polished_text"] == "嗯，今天把报告写一下吧。"

    failed = service.create_and_polish(1, {"original_text": "记得联系客户"}, lambda: (_ for _ in ()).throw(RuntimeError("model down")))
    assert failed["polish_status"] == "failed"
    assert failed["card"]["original_text"] == "记得联系客户"
    assert failed["card"]["polished_text"] is None
    assert changes[-1][3] == "upsert"


def test_feedback_is_account_isolated_and_can_be_corrected(tmp_path):
    service, _ = _service(tmp_path)
    card = service.create(1, {"original_text": "antigravity 真是战犯"})

    mood = service.record_classification_feedback(1, card["id"], "mood")
    todo = service.record_classification_feedback(1, card["id"], "todo")

    assert mood["label"] == "mood"
    assert todo["label"] == "todo"
    assert todo["run_id"] != mood["run_id"]
    with pytest.raises(FlashCardError) as invalid:
        service.record_classification_feedback(1, card["id"], "other")
    assert invalid.value.status == 422
    with pytest.raises(FlashCardError) as foreign:
        service.record_classification_feedback(2, card["id"], "mood")
    assert foreign.value.status == 404
    service.delete(1, card["id"])
    with pytest.raises(FlashCardError):
        service.record_classification_feedback(1, card["id"], "mood")


def test_feedback_reanalysis_replaces_pending_recommendations_but_preserves_added(tmp_path):
    service, _ = _service(tmp_path)
    pending = service.create(1, {"original_text": "计划整理厨房，然后洗碗并清台"})
    service.save_insights(1, pending["id"], "计划整理厨房，然后洗碗并清台。", None, [{"title": "规划厨房整理", "reason": "需要拆解"}])
    run = service.record_classification_feedback(1, pending["id"], "mood")
    service.save_feedback_reanalysis(1, pending["id"], run["run_id"], "今天真烦。", {"mood": "烦躁", "content": "我正在吐槽。"}, [])
    assert service.list_recommendations(1, [pending["id"]])[0]["superseded_at"]

    added = service.create(1, {"original_text": "记得倒垃圾"})
    service.save_insights(1, added["id"], "记得倒垃圾。", None, [{"title": "倒垃圾", "reason": "原文"}])
    recommendation = service.list_recommendations(1, [added["id"]])[0]
    service.mark_recommendation_added(1, recommendation["id"], "provider-task")
    run = service.record_classification_feedback(1, added["id"], "mood")
    service.save_feedback_reanalysis(1, added["id"], run["run_id"], "今天真烦。", {"mood": "烦躁", "content": "我正在吐槽。"}, [])
    assert service.list_recommendations(1, [added["id"]])[0]["status"] == "added"
