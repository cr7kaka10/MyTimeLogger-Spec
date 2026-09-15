import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server.server as server_module
from server.domain.flash_card_service import FlashCardService
from server.domain.flash_processing_log_service import FlashProcessingLogService
from server.domain.flash_skill_feedback_service import FlashSkillFeedbackService
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


def _mock_task_model(monkeypatch, response_content: str):
    calls = {"responses": iter(response_content if isinstance(response_content, list) else [response_content]), "requests": []}

    class FakeHttpClient:
        def close(self):
            pass

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.update(kwargs)
            calls["requests"].append(kwargs)
            response = next(calls["responses"])
            if isinstance(response, Exception):
                raise response
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])

    monkeypatch.setattr(server_module, "_load_user_provider_config", lambda *_: {
        "text_base_url": "https://ai.example/v1", "text_api_key": "test-key", "text_model": "test-model",
    })
    monkeypatch.setattr(server_module.httpx, "Client", lambda **_kwargs: FakeHttpClient())
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    return calls


def test_flash_card_ai_commands_are_scoped_and_never_apply_automatically():
    source = Path("server/server.py").read_text(encoding="utf-8")
    service = Path("server/domain/flash_card_service.py").read_text(encoding="utf-8")

    assert '@app.post("/api/timebook/flash-cards/{card_id}/polish")' in source
    assert '@app.post("/api/timebook/flash-cards/{card_id}/analyze")' not in source
    assert 'flash-todo-diary-extraction' in source
    assert 'flash_insight_analysis_failed' in source
    assert '_FLASH_TASK_INTENT_MARKERS' not in source and '_FLASH_EMOTION_MARKERS' not in source
    assert 'task_recommendations' in source
    assert 'diary_mood' in service
    assert 'diary_content' in service
    assert 'WHERE id=? AND user_id=?' in service


def test_flash_skill_candidate_gate_requires_fixed_and_human_feedback_sets(monkeypatch):
    skill = Path("server/skills/flash-todo-diary-extraction/SKILL.md").read_text(encoding="utf-8")
    assert server_module._flash_skill_candidate_contract(skill) == (True, "passed")
    assert server_module._flash_skill_candidate_contract("# Flash Todo Diary Extraction Skill") [0] is False

    def analysis(_user_id, text, _skill):
        if text == "这个功能吧，真的太烦了呀！":
            return {"polished_text": "这个功能，真的太烦了！", "todos": [], "diary": {"mood": "烦躁 😣", "content": "这个功能，真的太烦了！"}}
        corrected = {"切尔西买了一个有一个，三层巴士了！": "切尔西买了一个又一个，三层巴士了！", "我今夭很烦": "我今天很烦", "好烦烦啊": "好烦啊", "大约半个小时左右": "大约半个小时"}
        if text in corrected:
            return {"polished_text": corrected[text], "todos": [], "diary": None}
        return {"polished_text": text, "todos": [{"title": "带垃圾", "reason": "明确行动"}], "diary": None} if ("垃圾" in text or "整理" in text) else {"polished_text": text, "todos": [], "diary": {"mood": "烦躁 😣", "content": text}}

    monkeypatch.setattr(server_module, "_flash_todo_diary_analysis", analysis)
    samples = [
        {"kind": "classification", "input": "明天整理书桌", "expected_label": "todo"},
        {"kind": "classification", "input": "今天真烦", "expected_label": "mood"},
        {"kind": "polish", "input": "这个功能吧，真的太烦了呀！", "expected_output": "这个功能，真的太烦了！"},
    ]
    assert server_module._evaluate_flash_skill_candidate(1, skill, samples) == (True, "fixed_labels_and_proofreading_sets_passed")
    samples[-1]["expected_output"] = "模型不该重写"
    assert server_module._evaluate_flash_skill_candidate(1, skill, samples) == (False, "polish_retained_set_failed")

    def source_copy(_uid, text, _skill):
        return {"polished_text": text, "todos": [{"title": "带垃圾", "reason": "明确行动"}], "diary": None} if "垃圾" in text else {"polished_text": text, "todos": [], "diary": {"mood": "烦躁", "content": text}}

    monkeypatch.setattr(server_module, "_flash_todo_diary_analysis", source_copy)
    assert server_module._evaluate_flash_skill_candidate(1, skill, []) == (False, "fixed_polish_correction_failed")
    monkeypatch.setattr(server_module, "_flash_todo_diary_analysis", lambda _uid, text, _skill: analysis(_uid, text, _skill) | ({"polished_text": "正式分析说明。"} if text == "antigravity真是战犯啊！纯粹是卧底捣乱的！" else {}))
    assert server_module._evaluate_flash_skill_candidate(1, skill, []) == (False, "fixed_polish_preservation_failed")


def test_flash_polish_accepts_only_light_cleanup_and_preserves_literal_names():
    light = "这个功能吧，真的太烦了呀！"
    assert server_module._faithful_flash_polish(light, "这个功能，真的太烦了！") == "这个功能，真的太烦了！"
    source = "antigravity真是战犯呀！纯粹是卧底捣乱的！绝不让他改代码！纯瞎改！"
    rewritten = "antigravity真是战犯！纯粹是卧底捣乱！绝不让他改代码！纯瞎改！纯浪费时间！路边一条狗！"
    assert server_module._faithful_flash_polish(source, rewritten) == source
    assert server_module._faithful_flash_polish("用GPT-5.6检查3次", "用GPT检查三次") == "用GPT-5.6检查3次"


def test_flash_polish_accepts_minimal_corrections_and_preserves_ambiguous_voice():
    assert server_module._faithful_flash_polish("切尔西买了一个有一个，三层巴士了。", "切尔西买了一个又一个，三层巴士了。") == "切尔西买了一个又一个，三层巴士了。"
    assert server_module._faithful_flash_polish("我今夭很烦", "我今天很烦") == "我今天很烦"
    assert server_module._faithful_flash_polish("好烦烦啊", "好烦啊") == "好烦啊"
    raw = "antigravity真是战犯啊！纯粹是卧底捣乱的！"
    assert server_module._faithful_flash_polish(raw, raw) == raw
    assert server_module._faithful_flash_polish("切尔西买了一个有一个，三层巴士了！", "切尔西买了一个又一个，三层巴士了！") == "切尔西买了一个又一个，三层巴士了！"


def test_flash_polish_retries_once_after_rewrite_and_falls_back_when_still_invalid(monkeypatch):
    def payload(polished):
        return json.dumps({"polished_text": polished, "action_scope": "none", "action_state": "none", "action_evidence": "", "affect_scope": "current_experience", "affect_state": "emotion", "affect_evidence": "很烦", "todos": [], "diary": {"mood": "烦躁", "content": polished}})

    calls = _mock_task_model(monkeypatch, [payload("我今天对所有事情都感到非常生气，准备彻底改变生活。"), payload("我今天很烦")])
    result = server_module._flash_todo_diary_analysis(1, "我今夭很烦")
    assert result["polished_text"] == "我今天很烦"
    assert len(calls["requests"]) == 2 and "只修复上下文唯一确定" in calls["requests"][1]["messages"][0]["content"]
    assert result["attempts"][-1] == {"stage": "polish_retry", "code": "accepted"}

    calls = _mock_task_model(monkeypatch, [payload("我今天对所有事情都感到非常生气，准备彻底改变生活。"), payload("我必须立刻改变一切，绝不允许拖延。")])
    result = server_module._flash_todo_diary_analysis(1, "我今夭很烦")
    assert result["polished_text"] == "我今夭很烦" and len(calls["requests"]) == 2
    assert result["attempts"][-1] == {"stage": "polish_retry", "code": "fallback"}


@pytest.mark.parametrize("payload,key", [
    ({"polished_text": "他就是故意来浪费时间的。", "todos": [], "diary": {"mood": "烦躁", "content": "我被他的行为惹烦了。"}}, "diary"),
    ({"polished_text": "应该立刻彻底解决。", "todos": [{"task": "提交报告", "reason": "原文明示"}], "diary": None}, "todos"),
])
def test_unfaithful_polish_falls_back_without_dropping_valid_insights(payload, key):
    source = "我很烦" if key == "diary" else "提交报告"
    result = server_module._normalize_flash_semantics(payload, source)
    assert result["polished_text"] == source
    assert result[key]


def test_flash_recommendations_persist_status_and_keep_ignored_rows(tmp_path):
    store = ServerSleepStore(db_path=str(tmp_path / "recommendations.db"))
    service = FlashCardService(store._connect, store._record_server_change)
    with store._connect() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'recommendation-owner','test','2026-08-13 10:00:00')")
    card = service.create(1, {"original_text": "明天处理部署问题"})
    service.save_insights(1, card["id"], "明天处理部署问题。", None, [{"title": "处理部署问题", "reason": "明确待办"}])
    recommendation = service.list_recommendations(1, [card["id"]])[0]
    ignored = service.ignore_recommendation(1, recommendation["id"])

    assert ignored["status"] == "ignored" and ignored["ignored_at"]
    assert service.list_recommendations(1, [card["id"]])[0]["status"] == "ignored"
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_flash_task_recommendations WHERE id=?", (recommendation["id"],)).fetchone()[0] == 1


def test_flash_insight_skill_returns_a_candidate_and_diary(monkeypatch):
    calls = _mock_task_model(monkeypatch, json.dumps({
        "polished_text": "软件部署后进行封版，不再添加新功能。虽然紧张，但很踏实。",
        "action_state": "actionable", "action_evidence": "进行封版",
        "affect_state": "emotion", "affect_evidence": "很踏实",
        "todos": [{"task": "软件封版，停止新增功能", "reason": "闪念要求部署完成后封版"}],
        "diary": {"mood": "踏实", "emotion_family": "calm", "content": "我完成部署后准备封版，虽然紧张，但感到踏实。"},
    }))

    result = server_module._flash_todo_diary_analysis(7, "软件部署后，进行封版，不再添加新功能。虽然紧张，但很踏实。")

    assert result["todos"] == [{"title": "软件封版，停止新增功能", "reason": "闪念要求部署完成后封版"}]
    assert result["diary"]["mood"] == "踏实 😌"
    assert calls["messages"][0]["role"] == "system"
    assert "action_state" in calls["messages"][0]["content"]
    assert calls["messages"][1]["content"] == "软件部署后，进行封版，不再添加新功能。虽然紧张，但很踏实。"


def test_flash_insight_skill_allows_a_diary_without_creating_a_candidate(monkeypatch):
    _mock_task_model(monkeypatch, '{"polished_text":"今天的天空很好看。","todos":[],"diary":{"mood":"平静","content":"我看着今天的天空，感到平静。"}}')

    result = server_module._flash_todo_diary_analysis(7, "今天的天空很好看")
    assert result["todos"] == []
    assert result["diary"]["mood"] == "平静 😌"


def test_flash_insight_allows_missing_todos_for_a_pure_emotional_flash(monkeypatch):
    _mock_task_model(monkeypatch, '{"polished_text":"浪费了一天时间，真是让人烦躁。","diary":{"mood":"烦躁","content":"我觉得今天的时间被浪费了，感到很烦躁。"}}')

    result = server_module._flash_todo_diary_analysis(7, "浪费一天时间！操！")

    assert result["polished_text"] == "浪费一天时间！操！"
    assert result["todos"] == []
    assert result["diary"]["mood"] == "烦躁 😣"


def test_flash_insight_saves_polish_when_optional_fields_are_invalid(monkeypatch):
    calls = _mock_task_model(monkeypatch, '{"polished_text":"今天完成了部署。","todos":"invalid","diary":{"mood":"","content":""}}')

    result = server_module._flash_todo_diary_analysis(7, "今天完成了部署")

    assert result["polished_text"] == "今天完成了部署。"
    assert result["todos"] == []
    assert result["diary"] is None
    assert len(calls["requests"]) == 1


def test_flash_insight_recovers_a_missing_diary_for_explicit_emotion(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"猫太烦人了，早上总是叫唤吵醒我。","action_state":"actionable","action_evidence":"处理猫的叫声问题","affect_state":"emotion","affect_evidence":"太烦人了","todos":[{"task":"处理猫的叫声问题","reason":"早上被吵醒"}],"diary":null}',
        '{"polished_text":"猫太烦人了，早上总是叫唤吵醒我。","action_state":"actionable","action_evidence":"早上总是叫唤吵醒我","affect_state":"emotion","affect_evidence":"太烦人了","todos":[{"task":"处理猫的叫声问题","reason":"早上被吵醒"}],"diary":{"mood":"烦躁","emotion_family":"frustrated","content":"我因为猫早上持续叫唤把我吵醒，感到很烦躁。"}}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "猫太烦人了，早上总是叫唤吵醒我！")

    assert result["todos"][0]["title"] == "处理猫的叫声问题"
    assert result["diary"]["mood"] == "烦躁 😣"
    assert len(calls["requests"]) == 2


def test_flash_insight_keeps_candidates_when_single_diary_recovery_fails(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"猫太烦人了，早上总是叫唤吵醒我。","action_state":"actionable","action_evidence":"早上总是叫唤吵醒我","affect_state":"emotion","affect_evidence":"太烦人了","todos":[{"task":"处理猫的叫声问题","reason":"早上被吵醒"}],"diary":null}',
        '{"polished_text":"猫太烦人了。","action_state":"actionable","action_evidence":"不存在","affect_state":"emotion","affect_evidence":"不存在","todos":[],"diary":null}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "猫太烦人了，早上总是叫唤吵醒我！")

    assert result["diary"] is None
    assert result["todos"][0]["title"] == "处理猫的叫声问题"
    assert len(calls["requests"]) == 2


def test_flash_insight_recovers_a_missing_todo_for_a_short_explicit_action(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"试试千问输入法。","action_state":"actionable","action_evidence":"试试千问输入法","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
        '{"polished_text":"试试千问输入法。","action_state":"actionable","action_evidence":"试试千问输入法","affect_state":"none","affect_evidence":"","todos":[{"task":"尝试使用千问输入法","reason":"记录了明确的尝试动作"}],"diary":null}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "试试千问输入法")

    assert result["todos"] == [{"title": "尝试使用千问输入法", "reason": "记录了明确的尝试动作"}]
    assert result["diary"] is None
    assert result["attempts"][-1] == {"stage": "semantic_repair", "code": "done"}
    assert len(calls["requests"]) == 2


def test_flash_insight_does_not_recover_todos_for_an_objective_record(monkeypatch):
    calls = _mock_task_model(monkeypatch, '{"polished_text":"今天下雨了。","todos":[],"diary":null}')

    result = server_module._flash_todo_diary_analysis(7, "今天下雨了")

    assert result["todos"] == []
    assert result["diary"] is None
    assert len(calls["requests"]) == 1


def test_flash_insight_keeps_polish_when_todo_recovery_fails(monkeypatch):
    calls = _mock_task_model(monkeypatch, ['{"polished_text":"试试千问输入法。","action_state":"actionable","action_evidence":"试试千问输入法","affect_state":"none","affect_evidence":"","todos":[],"diary":null}', '{'])

    result = server_module._flash_todo_diary_analysis(7, "试试千问输入法")

    assert result["polished_text"] == "试试千问输入法。"
    assert result["todos"] == []
    assert result["attempts"][-1] == {"stage": "semantic_repair", "code": "invalid"}
    assert len(calls["requests"]) == 2


def test_flash_insight_uses_backup_only_when_primary_cannot_polish(monkeypatch):
    calls = _mock_task_model(monkeypatch, ['{}', '{"polished_text":"闪念。","todos":[],"diary":null}'])
    monkeypatch.setattr(server_module, "_load_user_provider_config", lambda *_: {
        "text_base_url": "https://main.example/v1", "text_api_key": "main-key", "text_model": "main",
        "text_backup_1_base_url": "https://backup.example/v1", "text_backup_1_api_key": "backup-key", "text_backup_1_model": "backup",
    })

    result = server_module._flash_todo_diary_analysis(7, "闪念")

    assert result["polished_text"] == "闪念。"
    assert [item["slot"] for item in result["attempts"]] == ["主模型", "备用模型 1"]


def test_flash_insight_keeps_primary_when_optional_fields_are_invalid(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"午睡完迷迷糊糊的，好烦呀","action_state":"none","action_evidence":"","affect_state":"emotion","affect_evidence":"好烦呀","todos":"invalid","diary":null}',
        '{"polished_text":"午睡完迷迷糊糊的，好烦呀","action_state":"none","action_evidence":"","affect_state":"emotion","affect_evidence":"好烦呀","todos":[],"diary":{"mood":"烦躁","emotion_family":"frustrated","content":"我午睡后迷迷糊糊，感到很烦躁。"}}',
    ])
    monkeypatch.setattr(server_module, "_load_user_provider_config", lambda *_: {
        "text_base_url": "https://main.example/v1", "text_api_key": "main-key", "text_model": "main",
        "text_backup_1_base_url": "https://backup.example/v1", "text_backup_1_api_key": "backup-key", "text_backup_1_model": "backup",
    })
    result = server_module._flash_todo_diary_analysis(7, "午睡完迷迷糊糊的，好烦呀")
    assert result["diary"]["mood"] == "烦躁 😣"
    assert [item["slot"] for item in result["attempts"] if "slot" in item] == ["主模型"]
    assert [request["model"] for request in calls["requests"]] == ["main", "main"]


def test_flash_future_wish_drops_invented_current_diary(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"真希望周末能去爬山。","action_state":"non_action","action_evidence":"真希望周末能去爬山","affect_scope":"future_attitude","affect_state":"emotion","affect_evidence":"真希望","todos":[],"diary":{"mood":"焦虑","emotion_family":"anxious","content":"我担心周末不能去爬山。"}}',
        '{"polished_text":"真希望周末能去爬山。","action_state":"non_action","action_evidence":"真希望周末能去爬山","affect_scope":"future_attitude","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "真希望周末能去爬山")

    assert result["diary"] is None
    assert result["attempts"][-1] == {"stage": "semantic_repair", "code": "done"}
    assert len(calls["requests"]) == 2


def test_flash_future_wish_keeps_explicit_current_feeling(monkeypatch):
    _mock_task_model(monkeypatch, '{"polished_text":"想到周末能爬山，我现在很开心。","action_state":"non_action","action_evidence":"想到周末能爬山","affect_scope":"current_experience","affect_state":"emotion","affect_evidence":"现在很开心","todos":[],"diary":{"mood":"开心","emotion_family":"pleasant","content":"想到周末能爬山，我现在感到很开心。"}}')

    result = server_module._flash_todo_diary_analysis(7, "想到周末能爬山，我现在很开心")

    assert result["diary"]["mood"] == "开心 😄"


def test_flash_english_mood_is_optional_and_does_not_drop_todo(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"把垃圾带下楼，屋里的味道让我很难受。","action_state":"actionable","action_evidence":"把垃圾带下楼","affect_scope":"current_experience","affect_state":"physical_feeling","affect_evidence":"很难受","todos":[{"task":"把垃圾带下楼","reason":"清理垃圾"}],"diary":{"mood":"discomfort","emotion_family":"discomfort","content":"屋里的味道让我很难受。"}}',
        '{',
    ])

    result = server_module._flash_todo_diary_analysis(7, "把垃圾带下楼，屋里的味道让我很难受")

    assert result["todos"][0]["title"] == "把垃圾带下楼"
    assert result["diary"] is None
    assert len(calls["requests"]) == 2


def test_flash_chinese_mood_keeps_family_emoji():
    assert server_module._valid_flash_diary({"mood": "难受", "emotion_family": "discomfort", "content": "屋里的味道让我很难受。"})["mood"] == "难受 😣"


def test_flash_family_in_affect_state_is_repaired_without_dropping_todo(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"把垃圾带下楼，屋里的味道让我很难受。","action_scope":"pending_action","action_state":"actionable","action_evidence":"把垃圾带下楼","affect_scope":"current_experience","affect_state":"discomfort","affect_evidence":"很难受","todos":[{"task":"把垃圾带下楼","reason":"清理垃圾"}],"diary":null}',
        '{"polished_text":"把垃圾带下楼，屋里的味道让我很难受。","action_scope":"pending_action","action_state":"actionable","action_evidence":"把垃圾带下楼","affect_scope":"current_experience","affect_state":"physical_feeling","affect_evidence":"很难受","todos":[{"task":"把垃圾带下楼","reason":"清理垃圾"}],"diary":{"mood":"难受","emotion_family":"discomfort","content":"屋里的味道让我很难受。"}}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "把垃圾带下楼，屋里的味道让我很难受")

    assert result["todos"][0]["title"] == "把垃圾带下楼"
    assert result["diary"]["mood"] == "难受 😣"
    assert len(calls["requests"]) == 2


def test_flash_meta_record_does_not_invent_followup_task(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"记录一下，今天开会讨论了同步方案。","action_scope":"meta_record","action_state":"actionable","action_evidence":"开会讨论了同步方案","affect_scope":"none","affect_state":"none","affect_evidence":"","todos":[{"task":"记录同步方案讨论结果","reason":"会议内容"}],"diary":null}',
        '{"polished_text":"记录一下，今天开会讨论了同步方案。","action_scope":"meta_record","action_state":"completed","action_evidence":"今天开会讨论了同步方案","affect_scope":"none","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "记录一下，今天开会讨论了同步方案")

    assert result["todos"] == []
    assert result["attempts"][-1] == {"stage": "semantic_repair", "code": "done"}
    assert len(calls["requests"]) == 2


@pytest.mark.parametrize(("original", "payload", "expected_task", "expected_mood"), [
    ("把闪念功能弄完善了", {"polished_text": "把闪念功能完善。", "action_state": "actionable", "action_evidence": "把闪念功能弄完善了", "affect_state": "none", "affect_evidence": "", "todos": [{"task": "完善闪念功能", "reason": "这是尚未完成的明确行动"}], "diary": None}, "完善闪念功能", None),
    ("我已经把闪念功能弄完善了", {"polished_text": "我已经完善了闪念功能。", "action_state": "completed", "action_evidence": "已经把闪念功能弄完善了", "affect_state": "none", "affect_evidence": "", "todos": [], "diary": None}, None, None),
    ("先别提交版本，等我检查完再说", {"polished_text": "先不要提交版本，等我检查完。", "action_state": "completed", "action_evidence": "先别提交版本", "affect_state": "none", "affect_evidence": "", "todos": [], "diary": None}, None, None),
    ("真希望以后能多出去走走", {"polished_text": "希望以后能多出去走走。", "action_state": "non_action", "action_evidence": "希望以后能多出去走走", "affect_state": "none", "affect_evidence": "", "todos": [], "diary": None}, None, None),
    ("天气好热呀！热死了！", {"polished_text": "天气太热了。", "action_state": "none", "action_evidence": "", "affect_state": "physical_feeling", "affect_evidence": "热死了", "todos": [], "diary": {"mood": "难受", "emotion_family": "discomfort", "content": "天气炎热让我感到很难受。"}}, None, "难受 😣"),
    ("今天最高温 35°C", {"polished_text": "今天最高温为 35°C。", "action_state": "none", "action_evidence": "", "affect_state": "none", "affect_evidence": "", "todos": [], "diary": None}, None, None),
    ("今天最高温35度，但我在空调房里很舒服", {"polished_text": "今天最高温 35 度，但我在空调房里很舒服。", "action_state": "none", "action_evidence": "", "affect_state": "physical_feeling", "affect_evidence": "很舒服", "todos": [], "diary": {"mood": "舒适", "emotion_family": "pleasant", "content": "虽然室外炎热，但我在空调房里感到很舒服。"}}, None, "舒适 😄"),
    ("把玄关那堆快递盒归拢掉，看着太乱心里堵得慌", {"polished_text": "把玄关的快递盒收拢起来，看着太乱让我心里很堵。", "action_state": "actionable", "action_evidence": "把玄关那堆快递盒归拢掉", "affect_state": "emotion", "affect_evidence": "心里堵得慌", "todos": [{"task": "收拢玄关的快递盒", "reason": "玄关堆放杂乱"}], "diary": {"mood": "烦闷", "emotion_family": "frustrated", "content": "玄关堆放的快递盒很乱，让我感到烦闷。"}}, "收拢玄关的快递盒", "烦闷 😣"),
    ("看着太乱心里堵得慌", {"polished_text": "看着太乱，心里堵得慌。", "action_state": "none", "action_evidence": "", "affect_state": "frustrated", "affect_evidence": "心里堵得慌", "todos": [], "diary": {"mood": "烦闷", "emotion_family": "frustrated", "content": "眼前的杂乱让我感到烦闷。"}}, None, "烦闷 😣"),
])
def test_flash_semantic_scenario_matrix(monkeypatch, original, payload, expected_task, expected_mood):
    _mock_task_model(monkeypatch, json.dumps(payload, ensure_ascii=False))

    result = server_module._flash_todo_diary_analysis(7, original)

    assert (result["todos"][0]["title"] if result["todos"] else None) == expected_task
    assert (result["diary"]["mood"] if result["diary"] else None) == expected_mood


def test_flash_semantic_conflict_is_repaired_once_without_keyword_routing(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"把阳台角落腾出来。","action_state":"actionable","action_evidence":"把阳台角落腾出来","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
        '{"polished_text":"把阳台角落腾出来。","action_state":"actionable","action_evidence":"把阳台角落腾出来","affect_state":"none","affect_evidence":"","todos":[{"task":"腾出阳台角落","reason":"原文包含尚未完成的明确行动"}],"diary":null}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "把阳台角落腾出来")

    assert result["todos"][0]["title"] == "腾出阳台角落"
    assert result["attempts"][-1] == {"stage": "semantic_repair", "code": "done"}
    assert len(calls["requests"]) == 2


def test_flash_completed_claim_is_reviewed_against_memo_context(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"把闪念功能弄完善了","action_state":"completed","action_evidence":"把闪念功能弄完善了","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
        '{"actor_kind":"explicit","actor_evidence":"我","candidate_task":"完善闪念功能"}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "把闪念功能弄完善了")

    assert result["todos"][0]["title"] == "完善闪念功能"
    assert result["todos"][0]["reason"] == "闪念中的备忘行动"
    assert result["attempts"][-1] == {"stage": "completion_review", "code": "actionable"}
    assert len(calls["requests"]) == 2


def test_flash_whole_sentence_cannot_be_actor_evidence(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"把闪念功能弄完善了","action_state":"completed","action_evidence":"把闪念功能弄完善了","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
        '{"actor_kind":"explicit","actor_evidence":"把闪念功能弄完善了","candidate_task":"完善闪念功能","candidate_reason":"改进功能"}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "把闪念功能弄完善了")

    assert result["todos"][0]["title"] == "完善闪念功能"
    assert result["attempts"][-1] == {"stage": "completion_review", "code": "actionable"}
    assert len(calls["requests"]) == 2


def test_flash_completed_claim_with_real_actor_stays_completed(monkeypatch):
    calls = _mock_task_model(monkeypatch, [
        '{"polished_text":"我已经完善了闪念功能。","action_state":"completed","action_evidence":"我已经把闪念功能弄完善了","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
        '{"polished_text":"我已经把闪念功能弄完善了","action_state":"completed","action_evidence":"我已经把闪念功能弄完善了","affect_state":"none","affect_evidence":"","todos":[],"diary":null}',
        '{"actor_kind":"explicit","actor_evidence":"我","candidate_task":"完善闪念功能","candidate_reason":"动作内容"}',
    ])

    result = server_module._flash_todo_diary_analysis(7, "我已经把闪念功能弄完善了")

    assert result["todos"] == []
    assert result["attempts"][-1] == {"stage": "completion_review", "code": "completed"}
    assert len(calls["requests"]) == 3


def test_flash_successful_but_invalid_contract_saves_original_instead_of_failing(monkeypatch):
    _mock_task_model(monkeypatch, ["不是 JSON", "仍然不是 JSON"])

    result = server_module._flash_todo_diary_analysis(7, "随手记一下这个想法")

    assert result["polished_text"] == "随手记一下这个想法"
    assert result["todos"] == [] and result["diary"] is None
    assert result["_polish_code"] == "polish_contract_invalid"


def test_flash_fails_only_when_every_model_call_fails(monkeypatch):
    _mock_task_model(monkeypatch, RuntimeError("provider unavailable"))

    with pytest.raises(server_module.FlashCardError) as exc_info:
        server_module._flash_todo_diary_analysis(7, "记录一条闪念")

    assert exc_info.value.code == "flash_insight_analysis_failed"


def test_feedback_label_forces_the_visible_flash_result(monkeypatch):
    _mock_task_model(monkeypatch, '{"polished_text":"antigravity 是来捣乱的。","action_scope":"none","action_state":"none","action_evidence":"","affect_scope":"current_experience","affect_state":"emotion","affect_evidence":"捣乱","todos":[{"task":"阻止 antigravity","reason":"模型误判"}],"diary":{"mood":"烦躁","emotion_family":"frustrated","content":"我在吐槽 antigravity。"}}')

    mood = server_module._flash_feedback_analysis(7, "antigravity真是战犯呀！纯粹是卧底捣乱的！", "mood")

    assert mood["todos"] == []
    assert mood["diary"]["mood"] == "烦躁 😣"


def test_feedback_todo_discards_model_diary(monkeypatch):
    _mock_task_model(monkeypatch, '{"polished_text":"把垃圾带下楼。","action_scope":"pending_action","action_state":"actionable","action_evidence":"把垃圾带下楼","affect_scope":"current_experience","affect_state":"emotion","affect_evidence":"烦","todos":[{"task":"把垃圾带下楼","reason":"原文"}],"diary":{"mood":"烦躁","emotion_family":"frustrated","content":"我觉得很烦。"}}')

    todo = server_module._flash_feedback_analysis(7, "把垃圾带下楼", "todo")

    assert todo["todos"][0]["title"] == "把垃圾带下楼"
    assert todo["diary"] is None


def test_feedback_api_starts_reanalysis_and_refreshes_the_owned_card(tmp_path, monkeypatch):
    db_path = tmp_path / "flash-feedback-api.db"
    test_store = ServerSleepStore(db_path=str(db_path))
    original_store, original_cards, original_logs = server_module.store, server_module.flash_card_service, server_module.flash_processing_log_service
    try:
        server_module.store = test_store
        server_module.flash_card_service = FlashCardService(test_store._connect, test_store._record_server_change)
        server_module.flash_processing_log_service = FlashProcessingLogService(test_store._connect)
        monkeypatch.setattr(server_module, "_flash_feedback_analysis", lambda *_args: {"polished_text": "antigravity 是来捣乱的。", "todos": [], "diary": {"mood": "烦躁", "content": "我在吐槽 antigravity。"}})
        client = TestClient(server_module.app)
        client.post("/auth/register", json={"username": "feedback-owner", "password": "password123"})
        token = client.post("/auth/login", json={"username": "feedback-owner", "password": "password123"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        card = client.post("/api/timebook/flash-cards", headers=headers, json={"original_text": "antigravity真是战犯呀！"}).json()

        response = client.post(f"/api/timebook/flash-cards/{card['id']}/classification-feedback", headers=headers, json={"label": "mood"})

        assert response.status_code == 200
        assert response.json()["feedback"]["label"] == "mood"
        assert server_module.flash_card_service.get(1, card["id"])["diary_mood"] == "烦躁"
    finally:
        server_module.store, server_module.flash_card_service, server_module.flash_processing_log_service = original_store, original_cards, original_logs


def test_polish_correction_and_skill_history_apis_are_scoped_and_idempotent(tmp_path, monkeypatch):
    test_store = ServerSleepStore(db_path=str(tmp_path / "flash-polish-api.db"))
    originals = server_module.store, server_module.flash_card_service, server_module.flash_skill_feedback_service
    try:
        server_module.store = test_store
        server_module.flash_card_service = FlashCardService(test_store._connect, test_store._record_server_change)
        server_module.flash_skill_feedback_service = FlashSkillFeedbackService(test_store._connect)
        monkeypatch.setattr(server_module, "_try_refresh_flash_skill", lambda _user_id: None)
        client = TestClient(server_module.app)
        client.post("/auth/register", json={"username": "polish-owner", "password": "password123"})
        owner_token = client.post("/auth/login", json={"username": "polish-owner", "password": "password123"}).json()["token"]
        client.post("/auth/register", json={"username": "polish-other", "password": "password123"})
        other_token = client.post("/auth/login", json={"username": "polish-other", "password": "password123"}).json()["token"]
        owner = {"Authorization": f"Bearer {owner_token}"}; other = {"Authorization": f"Bearer {other_token}"}
        card = client.post("/api/timebook/flash-cards", headers=owner, json={"original_text": "老头乐真傻逼！挡我半天！"}).json()
        payload = {"request_id": "same-request", "corrected_text": "老头乐真傻逼！挡我半天！"}

        saved = client.post(f"/api/timebook/flash-cards/{card['id']}/polish-corrections", headers=owner, json=payload)
        retried = client.post(f"/api/timebook/flash-cards/{card['id']}/polish-corrections", headers=owner, json=payload)
        assert saved.status_code == retried.status_code == 200
        assert saved.json()["card"]["original_text"] == card["original_text"]
        assert saved.json()["card"]["polished_text"] == payload["corrected_text"]
        assert client.post(f"/api/timebook/flash-cards/{card['id']}/polish-corrections", headers=owner, json={"request_id": "empty", "corrected_text": " "}).status_code == 422
        assert client.post(f"/api/timebook/flash-cards/{card['id']}/polish-corrections", headers=other, json={"request_id": "foreign", "corrected_text": "越权"}).status_code == 404
        with test_store._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM server_flash_polish_corrections").fetchone()[0] == 1

        samples = server_module.flash_skill_feedback_service.feedback_samples(1)
        candidate = server_module.flash_skill_feedback_service.create_candidate(1, "# Flash Todo Diary Extraction Skill\n新增保真规则", samples)
        server_module.flash_skill_feedback_service.evaluate_and_activate(1, candidate["id"], lambda _: (False, "regression"))
        page = client.get("/api/timebook/flash-skill/history?limit=1", headers=owner).json()
        next_page = client.get(f"/api/timebook/flash-skill/history?limit=1&cursor={page['next_cursor']}", headers=owner).json()
        assert page["events"] and next_page["events"] and page["events"][0]["id"] != next_page["events"][0]["id"]
        assert "老头乐" not in str(page) and "content" not in page["events"][0]
        assert client.get("/api/timebook/flash-skill/history", headers=other).json()["events"] == []
    finally:
        server_module.store, server_module.flash_card_service, server_module.flash_skill_feedback_service = originals


def test_record_flash_returns_temporary_candidates_without_creating_tasks(tmp_path, monkeypatch):
    db_path = tmp_path / "flash-task-api.db"
    test_store = ServerSleepStore(db_path=str(db_path))
    original_store = server_module.store
    original_sync_hub = server_module.sync_hub
    original_flash_cards = server_module.flash_card_service
    original_flash_logs = server_module.flash_processing_log_service

    class TestSyncDb:
        log_path = str(db_path)

    try:
        server_module.store = test_store
        server_module.sync_hub = SyncHub(TestSyncDb())
        server_module.flash_card_service = FlashCardService(test_store._connect, test_store._record_server_change)
        server_module.flash_processing_log_service = FlashProcessingLogService(test_store._connect)
        monkeypatch.setattr(server_module, "_flash_todo_diary_analysis", lambda _user_id, _text: {
            "polished_text": "软件部署后进行封版，不再添加新功能。",
            "todos": [{"title": "软件封版，停止新增功能", "reason": "闪念要求部署完成后封版"}],
            "diary": {"mood": "平静", "content": "我准备在部署完成后封版，心情平静。"},
        })
        client = TestClient(server_module.app)
        client.post("/auth/register", json={"username": "flash-owner", "password": "password123"})
        token = client.post("/auth/login", json={"username": "flash-owner", "password": "password123"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        with test_store._connect() as conn:
            task_count_before = conn.execute("SELECT COUNT(*) FROM server_tasks").fetchone()[0]

        recorded = client.post("/api/timebook/flash-cards/record", headers=headers, json={"original_text": "软件部署后，进行封版，不再添加新功能。"})

        assert recorded.status_code == 200
        body = recorded.json()
        assert body["card"]["original_text"] == "软件部署后，进行封版，不再添加新功能。"
        assert body["card"]["diary_mood"] == "平静"
        assert body["task_recommendations"][0]["title"] == "软件封版，停止新增功能"
        logs = client.get(f"/api/timebook/flash-processing-logs?flash_card_id={body['card']['id']}", headers=headers).json()["logs"]
        assert logs[0]["status"] == "done"
        assert logs[0]["prompt_version"] == server_module.FLASH_SKILL_BASE_VERSION
        with test_store._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM server_tasks").fetchone()[0] == task_count_before

        monkeypatch.setattr(server_module, "_flash_todo_diary_analysis", lambda *_args: (_ for _ in ()).throw(server_module.FlashCardError("flash_insight_analysis_failed", "闪念分析失败，请稍后重试", 502)))
        failed_analysis = client.post("/api/timebook/flash-cards/record", headers=headers, json={"original_text": "再检查一次封版清单"})
        assert failed_analysis.status_code == 200
        assert failed_analysis.json()["task_analysis_status"] == "failed"
        assert failed_analysis.json()["card"]["original_text"] == "再检查一次封版清单"
        client.post("/auth/register", json={"username": "flash-other", "password": "password123"})
        second_token = client.post("/auth/login", json={"username": "flash-other", "password": "password123"}).json()["token"]
        assert client.get(f"/api/timebook/flash-processing-logs?flash_card_id={body['card']['id']}", headers={"Authorization": f"Bearer {second_token}"}).json()["logs"] == []
    finally:
        server_module.store = original_store
        server_module.sync_hub = original_sync_hub
        server_module.flash_card_service = original_flash_cards
        server_module.flash_processing_log_service = original_flash_logs
