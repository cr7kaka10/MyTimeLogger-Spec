import asyncio
import gzip
import importlib.util
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from server.config_manager import ConfigManager
from server.webdav_backup import (
    S3BackupConfig,
    S3BackupService,
    S3ConfigStore,
    S3Client,
    apply_retention,
    build_snapshot,
    build_user_backup_prefix,
    restore_snapshot,
    upload_snapshot,
)


def _server_config(tmp_path, text=None):
    path = tmp_path / "server_config.json"
    if text:
        path.write_text(text, encoding="utf-8")
    return ConfigManager(str(path), legacy_path=str(tmp_path / "missing_legacy.jsonc"))


def _load_report_paths_module():
    path = Path(__file__).resolve().parents[2] / "server" / "skills" / "time-management" / "modules" / "report_paths.py"
    spec = importlib.util.spec_from_file_location("report_paths_for_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_config_defaults_and_secret_mask(tmp_path):
    store = S3ConfigStore(str(tmp_path / "s3.json"), config_manager=_server_config(tmp_path))
    assert store.load().enabled is True
    assert store.load().bucket == "obss3"
    assert store.load().sqlite_prefix == "sqlite"
    with pytest.raises(ValueError, match="服务管理者"):
        store.save({"endpoint": "https://s3.example", "access_key": "u", "secret_key": "s", "enabled": True})
    public = S3BackupConfig(endpoint="https://s3.example", access_key="u", secret_key="s").public()
    assert public["endpoint"] == "https://s3.example"
    assert public["secret_configured"] is True
    assert "secret_key" not in public
    assert "shared_secret_scope" not in public


def test_user_backup_prefix_is_isolated_by_environment_and_registered_user():
    prefix_a = build_user_backup_prefix("testing", "mom", 2, "sqlite")
    prefix_b = build_user_backup_prefix("testing", "dad", 3, "sqlite")

    assert prefix_a == "testing/users/mom-2/sqlite"
    assert prefix_b == "testing/users/dad-3/sqlite"
    assert prefix_a != prefix_b


def test_current_user_uses_latest_s3_path(monkeypatch):
    monkeypatch.setenv("MYTIMELOGGER_ENVIRONMENT", "testing")
    config = S3BackupConfig(sqlite_prefix="legacy-dev", reports_prefix="E-日记")

    assert config.account_sqlite_prefix("redacted@example.com", 1) == "testing/users/redacted-example.com-1/sqlite"
    assert config.account_reports_prefix("redacted@example.com", 1) == "testing/users/redacted-example.com-1/reports"


def test_two_accounts_use_independent_s3_paths(monkeypatch):
    monkeypatch.setenv("MYTIMELOGGER_ENVIRONMENT", "testing")
    config = S3BackupConfig(endpoint="https://s3", access_key="u", secret_key="secret")

    first_prefix = config.account_sqlite_prefix("redacted@example.com", 1)
    child_prefix = config.account_sqlite_prefix("new@example.com", 2)

    assert child_prefix == "testing/users/new-example.com-2/sqlite"
    assert child_prefix != first_prefix


def test_report_output_defaults_to_project_assets_tmp(monkeypatch):
    module = _load_report_paths_module()
    monkeypatch.delenv("MYTIMELOGGER_REPORTS_DIR", raising=False)
    monkeypatch.delenv("MYTIMELOGGER_SERVER_MODE", raising=False)
    monkeypatch.setattr(module, "_config_reports_dir", lambda: "")
    assert module.resolve_reports_dir() == Path(__file__).resolve().parents[2] / "assets" / "tmp"


def test_legacy_config_is_not_loaded_as_shared_config(tmp_path):
    path = tmp_path / "s3.json"
    path.write_text(json.dumps({
        "sqlite_endpoint": "https://sqlite.example",
        "sqlite_bucket": "sqlite-bucket",
        "sqlite_access_key": "sqlite-user",
        "sqlite_secret_key": "sqlite-secret",
        "database_prefix": "dev",
        "reports_endpoint": "https://reports.example",
        "reports_bucket": "reports-bucket",
        "reports_access_key": "reports-user",
        "reports_secret_key": "reports-secret",
        "reports_prefix": "E-日记",
    }), encoding="utf-8")
    config = S3ConfigStore(str(path), config_manager=_server_config(tmp_path)).load()
    assert config.endpoint == ""
    assert config.bucket == "obss3"
    assert config.access_key == ""
    assert config.secret_key == ""


def test_invalid_retention_config_rejected(tmp_path):
    store = S3ConfigStore(str(tmp_path / "s3.json"), config_manager=_server_config(tmp_path))
    with pytest.raises(ValueError):
        store.save({"retention_count": 0})
    with pytest.raises(ValueError):
        store.save({"interval_hours": 0})


def test_snapshot_is_restorable_and_preserves_tables(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO sample(note) VALUES ('hello')")
    gz_path, manifest = build_snapshot(str(source), str(tmp_path))
    manifest_path = tmp_path / f"{gz_path.name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "restored.db"
    result = restore_snapshot(str(gz_path), str(manifest_path), str(output))
    assert result["tables"] == ["sample"]
    with sqlite3.connect(output) as conn:
        assert conn.execute("SELECT note FROM sample").fetchone()[0] == "hello"


def test_restore_rejects_damaged_snapshot(tmp_path):
    gz_path = tmp_path / "broken.db.gz"
    with gzip.open(gz_path, "wb") as file:
        file.write(b"not sqlite")
    manifest = {"size": gz_path.stat().st_size, "sha256": "bad"}
    manifest_path = tmp_path / "broken.db.gz.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError):
        restore_snapshot(str(gz_path), str(manifest_path), str(tmp_path / "out.db"))


def test_upload_snapshot_writes_backup_and_manifest(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER)")
    uploads = {}

    class FakeClient:
        def __init__(self, _config): pass
        def upload_bytes(self, key, data): uploads[key] = data
        def list_keys(self, _prefix): return []
        def delete(self, _path): pass

    monkeypatch.setattr("server.webdav_backup.S3Client", FakeClient)
    monkeypatch.setenv("MYTIMELOGGER_ENVIRONMENT", "testing")
    result = upload_snapshot(
        str(source),
        S3BackupConfig(endpoint="https://s3", bucket="root", sqlite_prefix="dev"),
        username="mom",
        user_id=2,
    )
    assert result["remote_path"] in uploads
    assert result["remote_path"].startswith("testing/service-backups/sqlite/")
    assert result["manifest_path"] in uploads


def test_retention_deletes_s3_objects_older_than_15_days():
    deleted = []
    listed = []
    old_stamp = (datetime.now() - timedelta(days=16)).strftime("%Y%m%d_%H%M%S")
    new_stamp = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d_%H%M%S")

    class FakeClient:
        def list_keys(self, prefix):
            listed.append(prefix)
            return [
                f"development/service-backups/sqlite/mtl_server_{old_stamp}.db.gz",
                f"development/service-backups/sqlite/mtl_server_{old_stamp}.db.gz.manifest.json",
                f"development/service-backups/sqlite/mtl_server_{new_stamp}.db.gz",
                "notes.txt",
            ]
        def delete(self, path): deleted.append(path)

    apply_retention(FakeClient(), S3BackupConfig(bucket="root", sqlite_prefix="dev", retention_count=1), username="mom", user_id=2)
    assert f"development/service-backups/sqlite/mtl_server_{old_stamp}.db.gz" in deleted
    assert f"development/service-backups/sqlite/mtl_server_{old_stamp}.db.gz.manifest.json" in deleted
    assert listed == ["development/service-backups/sqlite"]
    assert all(new_stamp not in path for path in deleted)
    assert all("notes.txt" not in path for path in deleted)


def test_service_reload_and_report_upload(tmp_path, monkeypatch):
    service = S3BackupService(str(tmp_path / "source.db"), str(tmp_path / "config.json"))
    service.store.config_manager = _server_config(tmp_path)
    service.reload(True)
    assert service.state["status"] == "queued"
    service.reload(False)
    assert service.state["status"] == "disabled"

    report = tmp_path / "report.md"
    report.write_text("ok", encoding="utf-8")
    config = S3BackupConfig(enabled=True, endpoint="https://s3", access_key="u", secret_key="s")
    uploaded = {}

    class FakeClient:
        def __init__(self, _config): pass
        def upload_bytes(self, key, data): uploaded[key] = data

    monkeypatch.setattr("server.webdav_backup.S3Client", FakeClient)
    service.upload_report_with_config(config, str(report), username="mom", user_id=2)
    assert service.state["report_last_remote_path"]
    assert service.state["report_last_remote_path"].startswith("development/users/mom-2/reports/")
    assert uploaded
    assert not report.exists()


def test_service_uses_injected_config_loader_for_each_run(tmp_path, monkeypatch):
    current = {"config": S3BackupConfig(enabled=True, endpoint="https://first", secret_key="one")}
    service = S3BackupService(
        str(tmp_path / "source.db"),
        str(tmp_path / "config.json"),
        config_loader=lambda: current["config"],
    )
    uploaded = []
    monkeypatch.setattr(
        "server.webdav_backup.upload_snapshot",
        lambda _path, config: uploaded.append(config.endpoint)
        or {"remote_path": "db/x.db.gz", "size": 1, "retention_error": None},
    )

    asyncio.run(service.run_once())
    current["config"] = S3BackupConfig(enabled=True, endpoint="https://second", secret_key="two")
    asyncio.run(service.run_once())
    current["config"] = S3BackupConfig(enabled=False)
    assert service.reload_config().enabled is False

    assert uploaded == ["https://first", "https://second"]
    assert service.state["status"] == "disabled"


def test_manual_run_reuses_lock_and_preserves_last_success_on_failure(tmp_path, monkeypatch):
    service = S3BackupService(str(tmp_path / "source.db"), str(tmp_path / "config.json"), lambda: S3BackupConfig(enabled=True, endpoint="https://s3", secret_key="s"))
    active = maximum = 0
    def upload(*_):
        nonlocal active, maximum
        active += 1; maximum = max(maximum, active); time.sleep(0.01); active -= 1
        return {"remote_path": "sqlite/first.db.gz", "size": 1, "retention_error": None}
    monkeypatch.setattr("server.webdav_backup.upload_snapshot", upload)
    async def run_twice():
        await asyncio.gather(service.run_now(), service.run_now())
    asyncio.run(run_twice())
    assert maximum == 1 and service.state["last_success"] and service.public_state()["last_remote_path"] == "sqlite/first.db.gz"
    monkeypatch.setattr("server.webdav_backup.upload_snapshot", lambda *_: (_ for _ in ()).throw(RuntimeError("CERTIFICATE_VERIFY_FAILED")))
    state = asyncio.run(service.run_now())
    assert state["status"] == "error" and state["last_remote_path"] == "sqlite/first.db.gz" and "CERTIFICATE_VERIFY_FAILED" in state["error"]


def test_two_services_load_s3_from_their_own_sqlite_database(tmp_path):
    def create_database(name, endpoint):
        path = tmp_path / name
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE config (value TEXT)")
            conn.execute("INSERT INTO config VALUES (?)", (json.dumps({"endpoint": endpoint}),))
        return path

    def loader(path):
        def load():
            with sqlite3.connect(path) as conn:
                row = conn.execute("SELECT value FROM config").fetchone()
            return S3BackupConfig(**json.loads(row[0])) if row else S3BackupConfig()
        return load

    development = create_database("development.db", "https://development-s3")
    testing = create_database("testing.db", "https://testing-s3")
    development_service = S3BackupService("dev.db", str(tmp_path / "dev.json"), loader(development))
    testing_service = S3BackupService("test.db", str(tmp_path / "test.json"), loader(testing))

    assert development_service._load_config().endpoint == "https://development-s3"
    assert testing_service._load_config().endpoint == "https://testing-s3"


def test_report_upload_failure_keeps_local_file(tmp_path, monkeypatch):
    service = S3BackupService(str(tmp_path / "source.db"), str(tmp_path / "config.json"))
    service.store.config_manager = _server_config(tmp_path)
    report = tmp_path / "report.md"
    report.write_text("ok", encoding="utf-8")
    config = S3BackupConfig(enabled=True, endpoint="https://s3", access_key="u", secret_key="s")

    class FakeClient:
        def __init__(self, _config): pass
        def upload_bytes(self, _key, _data): raise RuntimeError("boom")

    monkeypatch.setattr("server.webdav_backup.S3Client", FakeClient)
    service.upload_report_with_config(config, str(report), username="mom", user_id=2)
    assert report.exists()
    assert "boom" in service.state["report_error"]


def test_sleeping_worker_wakes_without_concurrency(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER)")
    service = S3BackupService(str(source), str(tmp_path / "config.json"))
    service.store.config_manager = _server_config(tmp_path)
    monkeypatch.setattr(service.store, "load", lambda: S3BackupConfig(enabled=True, endpoint="https://s3", access_key="u", secret_key="s"))
    active = total = maximum = 0

    def fake_upload(*_):
        nonlocal active, total, maximum
        active += 1; total += 1; maximum = max(maximum, active)
        time.sleep(0.02)
        active -= 1
        return {"remote_path": "db/x.db.gz", "size": 1, "retention_error": None}

    monkeypatch.setattr("server.webdav_backup.upload_snapshot", fake_upload)

    async def exercise():
        runner = asyncio.create_task(service.run())
        await asyncio.sleep(0.01)
        service.reload(True)
        await asyncio.wait_for(_wait_for(lambda: service.state["status"] == "success"), 1)
        await asyncio.gather(service.run_once(), service.run_once())
        service.stop()
        await runner

    asyncio.run(exercise())
    assert total >= 3
    assert maximum == 1


def test_client_tests_current_user_credentials_with_independent_prefixes(monkeypatch):
    calls = []

    class FakeBoto:
        def put_object(self, **kwargs):
            calls.append(("put", kwargs))
        def delete_object(self, **kwargs):
            calls.append(("delete", kwargs))
        def list_objects_v2(self, **kwargs):
            calls.append(("list", kwargs))
            return {"Contents": []}

    monkeypatch.setattr(S3Client, "_create_client", lambda self: FakeBoto())
    config = S3BackupConfig(
        endpoint="https://notes.example",
        bucket="obss3",
        sqlite_prefix="dev",
        reports_prefix="E-日记",
    )
    assert S3Client(config.sqlite_target()).test(config.account_sqlite_prefix("mom", 2)) == "obss3/development/users/mom-2/sqlite"
    assert S3Client(config.reports_target()).test(config.account_reports_prefix("mom", 2)) == "obss3/development/users/mom-2/reports"
    assert S3Client(config.sqlite_target()).list_keys(config.account_sqlite_prefix("mom", 2)) == []
    assert calls[0][1]["Bucket"] == "obss3"
    assert calls[0][1]["Key"] == "development/users/mom-2/sqlite/_mytimelogger_s3_test.txt"
    assert calls[2][1]["Bucket"] == "obss3"
    assert calls[2][1]["Key"] == "development/users/mom-2/reports/_mytimelogger_s3_test.txt"
    assert calls[4][1]["Bucket"] == "obss3"
    assert calls[4][1]["Prefix"] == "development/users/mom-2/sqlite/"


def test_client_adds_https_scheme_by_default():
    class FakeBoto:
        pass

    original = S3Client._create_client
    S3Client._create_client = lambda self: FakeBoto()
    try:
        client = S3Client(S3BackupConfig(endpoint="s3.cstcloud.cn").sqlite_target())
        assert client.endpoint == "https://s3.cstcloud.cn"
    finally:
        S3Client._create_client = original


def test_client_disables_optional_checksum_for_s3_compatible_services(monkeypatch):
    captured = {}

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return object()

    monkeypatch.setitem(__import__("sys").modules, "boto3", FakeBoto3)
    client = S3Client(S3BackupConfig(endpoint="s3.example", bucket="bucket").sqlite_target())
    config = captured["kwargs"]["config"]
    assert client.endpoint == "https://s3.example"
    assert captured["args"] == ("s3",)
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"


async def _wait_for(predicate):
    while not predicate():
        await asyncio.sleep(0.005)
