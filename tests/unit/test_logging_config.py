# -*- coding: utf-8 -*-
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.logging_config import (
    LoggingConfigStore,
    configure_logging,
    format_module_levels,
    parse_log_level,
    parse_module_levels,
    request_logging_middleware,
    traced,
)


def test_parse_log_level_and_module_overrides():
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level("WARNING") == logging.WARNING
    assert parse_log_level("bad", logging.ERROR) == logging.ERROR
    assert parse_module_levels("server.sync_hub=DEBUG, server.ticktick_client=warning") == {
        "server.sync_hub": logging.DEBUG,
        "server.ticktick_client": logging.WARNING,
    }


def test_configure_logging_is_idempotent_and_module_override_wins(tmp_path):
    root = logging.getLogger()
    before_handlers = list(root.handlers)
    try:
        root.handlers = []
        log_dir = str(tmp_path / "log")
        configure_logging(
            log_dir=log_dir,
            global_level="WARNING",
            module_levels="server.sync_hub=DEBUG",
            logger_names=["server.sync_hub", "server.ticktick_client"],
        )
        first_count = len(root.handlers)
        configure_logging(
            log_dir=log_dir,
            global_level="WARNING",
            module_levels="server.sync_hub=DEBUG",
            logger_names=["server.sync_hub", "server.ticktick_client"],
        )
        assert len(root.handlers) == first_count == 2
        assert logging.getLogger().level == logging.WARNING
        assert logging.getLogger("server.sync_hub").level == logging.DEBUG
        assert logging.getLogger("server.ticktick_client").level == logging.WARNING
    finally:
        root.handlers = before_handlers


def test_configure_logging_applies_global_level_to_default_loggers(tmp_path):
    root = logging.getLogger()
    before_handlers = list(root.handlers)
    try:
        root.handlers = []
        configure_logging(log_dir=str(tmp_path / "log"), global_level="WARNING")

        assert logging.getLogger("server.request").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
    finally:
        root.handlers = before_handlers


def test_configure_logging_applies_canonical_override_to_direct_script_alias(tmp_path):
    root = logging.getLogger()
    before_handlers = list(root.handlers)
    try:
        root.handlers = []
        configure_logging(
            log_dir=str(tmp_path / "log"),
            global_level="WARNING",
            module_levels="server.sync_hub=DEBUG",
        )
        assert logging.getLogger("server.sync_hub").level == logging.DEBUG
        assert logging.getLogger("sync_hub").level == logging.DEBUG

        configure_logging(log_dir=str(tmp_path / "log"), global_level="ERROR", module_levels="")
        assert logging.getLogger("server.sync_hub").level == logging.ERROR
        assert logging.getLogger("sync_hub").level == logging.ERROR
        assert logging.getLogger("server.request").level == logging.ERROR
    finally:
        root.handlers = before_handlers


def test_logging_config_store_persists_and_rejects_invalid_levels(tmp_path):
    store = LoggingConfigStore(str(tmp_path / "logging_config.json"))

    saved = store.save({
        "global_level": "warning",
        "module_levels": {"server.sync_hub": "debug"},
    })

    assert saved.global_level == "WARNING"
    assert saved.module_levels == {"server.sync_hub": "DEBUG"}
    assert store.load().module_levels == {"server.sync_hub": "DEBUG"}
    assert format_module_levels(saved.module_levels) == "server.sync_hub=DEBUG"

    with pytest.raises(ValueError, match="不支持的日志级别"):
        store.save({"global_level": "verbose"})


def test_invalid_module_level_preserves_file_and_runtime_level(tmp_path):
    store = LoggingConfigStore(str(tmp_path / "logging_config.json"))
    store.save({"global_level": "WARNING", "module_levels": {"server.sync_hub": "ERROR"}})
    before = store.path.read_text(encoding="utf-8")
    target = logging.getLogger("server.sync_hub")
    target.setLevel(logging.ERROR)

    with pytest.raises(ValueError, match="不支持的日志级别"):
        store.save({"module_levels": {"server.sync_hub": "verbose"}})

    assert store.path.read_text(encoding="utf-8") == before
    assert target.level == logging.ERROR


def test_traced_logs_success_and_reraises_exception(caplog):
    logger_name = __name__

    @traced("unit.success", level=logging.INFO)
    def ok():
        return "done"

    @traced("unit.failure", level=logging.INFO)
    def fail():
        raise RuntimeError("boom")

    with caplog.at_level(logging.INFO, logger=logger_name):
        assert ok() == "done"
        with pytest.raises(RuntimeError, match="boom"):
            fail()

    messages = [record.getMessage() for record in caplog.records]
    assert any("unit.success start" in message for message in messages)
    assert any("unit.success ok" in message for message in messages)
    assert any("unit.failure error" in message for message in messages)


def test_request_logging_middleware_logs_request_context(caplog):
    app = FastAPI()
    app.middleware("http")(request_logging_middleware)

    @app.get("/ping")
    def ping():
        return {"status": "ok"}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="server.request"):
        response = client.get("/ping", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test"
    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "method=GET" in message
    assert "path=/ping" in message
    assert "status=200" in message
    assert "request_id=req-test" in message
