# -*- coding: utf-8 -*-
import sqlite3
import inspect

import server.server as server_module


def test_locked_flash_migration_is_retried_without_crashing_server_startup(monkeypatch):
    calls = []

    class LockedThenReady:
        def migrate_legacy_recommendations(self):
            calls.append("attempt")
            if len(calls) < 3:
                raise sqlite3.OperationalError("database is locked")
            return 2

    monkeypatch.setattr(server_module, "flash_card_service", LockedThenReady())
    monkeypatch.setattr(server_module.time, "sleep", lambda _seconds: None)

    assert server_module._migrate_flash_recommendations_on_startup() == 2
    assert len(calls) == 3


def test_persistent_locked_flash_migration_is_deferred(monkeypatch):
    class AlwaysLocked:
        def migrate_legacy_recommendations(self):
            raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_module, "flash_card_service", AlwaysLocked())
    monkeypatch.setattr(server_module.time, "sleep", lambda _seconds: None)

    assert server_module._migrate_flash_recommendations_on_startup() == 0


def test_flash_pollution_repair_runs_before_metadata_migration():
    source = inspect.getsource(server_module.lifespan)
    assert source.index("_repair_flash_task_pollution_on_startup()") < source.index("_migrate_flash_recommendations_on_startup()")


def test_flash_pollution_repair_failure_does_not_block_startup(monkeypatch):
    class BrokenRepair:
        def repair(self):
            raise RuntimeError("forced repair failure")

    monkeypatch.setattr(server_module, "flash_task_pollution_repair_service", BrokenRepair())
    assert server_module._repair_flash_task_pollution_on_startup() == {
        "status": "deferred", "error": "RuntimeError",
    }


def test_start_script_passes_current_build_to_server_ping_contract():
    script = open("scripts/start-local-process.ps1", encoding="utf-8").read()
    assert "MTL_BUILD_REVISION=$expectedBuild" in script
    assert "${serverBuildEnvironment}python -m uvicorn server.server:app" in script
