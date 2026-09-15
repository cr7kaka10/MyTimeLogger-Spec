# -*- coding: utf-8 -*-
import sqlite3

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


def test_start_script_passes_current_build_to_server_ping_contract():
    script = open("scripts/start-local-process.ps1", encoding="utf-8").read()
    assert "MTL_BUILD_REVISION=$expectedBuild" in script
    assert "${serverBuildEnvironment}python -m uvicorn server.server:app" in script
