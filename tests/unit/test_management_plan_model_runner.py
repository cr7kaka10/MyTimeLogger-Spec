import json

import httpx
import openai
import pytest

from server import server
from server.domain.management_plan_service import ManagementPlanError


class _HttpClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    def close(self):
        self.closed = True


def _runner(monkeypatch, openai_factory):
    config = {
        "text_base_url": "https://model.example/v1",
        "text_api_key": "test-key",
        "text_model": "test-model",
    }
    clients = []

    def build_http_client(**kwargs):
        client = _HttpClient(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(server, "_load_user_provider_config", lambda *_: config)
    monkeypatch.setattr(server.httpx, "Client", build_http_client)
    monkeypatch.setattr(openai, "OpenAI", openai_factory)
    return server._management_plan_model_runner(1), clients


def test_model_runner_uses_direct_verified_transport_and_parses_json(monkeypatch):
    observed = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            observed.update(kwargs)
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            observed["request"] = kwargs
            message = type("Message", (), {"content": json.dumps({"schema_version": "1"})})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    runner, clients = _runner(monkeypatch, FakeOpenAI)

    assert runner("生成方案", {"domains": {}}) == {"schema_version": "1"}
    assert clients[0].kwargs == {"trust_env": False}
    assert clients[0].closed is True
    assert observed["http_client"] is clients[0]
    assert observed["request"]["response_format"] == {"type": "json_object"}
    assert "reward.weekend-game" in observed["request"]["messages"][0]["content"]
    assert "action 只能是 create、update、bind、keep、disable" in observed["request"]["messages"][0]["content"]


def test_model_runner_maps_connection_error_without_sensitive_detail(monkeypatch):
    class FakeConnectionError(Exception):
        pass

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **_kwargs):
            raise FakeConnectionError("test-key request body")

    monkeypatch.setattr(openai, "APIConnectionError", FakeConnectionError)
    runner, clients = _runner(monkeypatch, FakeOpenAI)

    with pytest.raises(ManagementPlanError) as error:
        runner("secret request", {})

    assert error.value.code == "ai_connection_failed"
    assert "test-key" not in str(error.value)
    assert clients[0].closed is True


def test_model_runner_maps_provider_error_without_sensitive_detail(monkeypatch):
    class FakeStatusError(Exception):
        status_code = 401

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **_kwargs):
            raise FakeStatusError("test-key provider response")

    monkeypatch.setattr(openai, "APIStatusError", FakeStatusError)
    runner, clients = _runner(monkeypatch, FakeOpenAI)

    with pytest.raises(ManagementPlanError) as error:
        runner("secret request", {})

    assert error.value.code == "ai_provider_failed"
    assert "test-key" not in str(error.value)
    assert clients[0].closed is True


def test_model_runner_maps_raw_http_error(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **_kwargs):
            raise httpx.ReadTimeout("request body")

    runner, _ = _runner(monkeypatch, FakeOpenAI)

    with pytest.raises(ManagementPlanError) as error:
        runner("secret request", {})

    assert error.value.code == "ai_connection_failed"


def test_model_runner_normalizes_only_the_logical_key_namespace(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **_kwargs):
            content = json.dumps({"items": [{"logical_key": "reward_item.weekend_game", "type": "reward_item"}]})
            message = type("Message", (), {"content": content})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    runner, _ = _runner(monkeypatch, FakeOpenAI)

    assert runner("生成方案", {})["items"][0]["logical_key"] == "reward-item.weekend_game"


def test_model_runner_replaces_invalid_generated_keys_with_type_scoped_identifiers(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **_kwargs):
            content = json.dumps({"items": [
                {"logical_key": "task.还款信用卡", "type": "ticktick_task", "title": "还款信用卡"},
                {"logical_key": "task.还款信用卡", "type": "ticktick_task", "title": "另一项任务"},
            ]}, ensure_ascii=False)
            message = type("Message", (), {"content": content})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    runner, _ = _runner(monkeypatch, FakeOpenAI)
    items = runner("生成方案", {})["items"]

    assert [item["logical_key"] for item in items] == ["task.item-1", "task.item-2"]
    assert items[0]["title"] == "还款信用卡"


def test_model_runner_converts_generated_sleep_items_to_goals(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **_kwargs):
            message = type("Message", (), {"content": json.dumps({"items": [{"logical_key": "sleep.weekly", "type": "sleep", "action": "update"}]})})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    runner, _ = _runner(monkeypatch, FakeOpenAI)

    assert runner("生成方案", {})["items"][0]["type"] == "goal"


def test_model_runner_includes_the_review_policy_without_provider_configuration(monkeypatch):
    observed = {}

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            observed.update(kwargs)
            message = type("Message", (), {"content": json.dumps({"items": [], "review": {}})})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    runner, _ = _runner(monkeypatch, FakeOpenAI)
    runner("总结当前方案", {"planning_intent": "review", "policy_version": "management-planning-v1"})
    prompt = observed["messages"][0]["content"]
    assert "review 模式" in prompt
    assert "management-planning-v3" in prompt
    assert "management-planning-skill-v2" in prompt
    assert "不得编造金币、商品、价格、解锁条件或来源" in prompt
    assert "禁止在输出中提供或覆盖 `evidence`" in prompt
    assert "所有面向用户的自然语言字段必须使用简体中文" in prompt
    assert "test-key" not in prompt


def test_model_runner_normalizes_review_strings(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **_kwargs): self.chat = type("Chat", (), {"completions": self})()
        def create(self, **_kwargs):
            message = type("Message", (), {"content": json.dumps({"items": [], "review": {"strengths": "已有规则", "risks": "奖励不足", "recommendations": "补充商品"}})})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()
    runner, _ = _runner(monkeypatch, FakeOpenAI)
    review = runner("总结", {"planning_intent": "review"})["review"]
    assert review == {"strengths": ["已有规则"], "risks": ["奖励不足"], "recommendations": ["补充商品"]}


def test_model_runner_normalizes_review_that_omits_items(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **_kwargs): self.chat = type("Chat", (), {"completions": self})()
        def create(self, **_kwargs):
            message = type("Message", (), {"content": json.dumps({"review": {"strengths": ["已有规则"], "risks": ["奖励不足"], "recommendations": ["补充商品"]}})})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()
    runner, _ = _runner(monkeypatch, FakeOpenAI)
    payload = runner("总结", {"planning_intent": "review"})
    assert payload["items"] == []


def test_model_runner_falls_back_to_summary_when_review_is_omitted(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **_kwargs): self.chat = type("Chat", (), {"completions": self})()
        def create(self, **_kwargs):
            message = type("Message", (), {"content": json.dumps({"summary": "已建立基础方案", "items": []})})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()
    runner, _ = _runner(monkeypatch, FakeOpenAI)
    payload = runner("总结", {"planning_intent": "review"})
    assert payload["review"]["strengths"] == ["已建立基础方案"]
