from pathlib import Path


def test_s3_module_exposes_report_upload_only():
    source = (Path(__file__).resolve().parents[2] / "server" / "webdav_backup.py").read_text(encoding="utf-8")
    assert "def upload_snapshot(" not in source
    assert "def create_sqlite_snapshot(" not in source
    assert "async def run_once(" not in source
    assert "async def run_now(" not in source
    assert "async def run(self)" not in source


def test_report_upload_uses_user_scoped_reports_prefix(tmp_path, monkeypatch):
    from server.webdav_backup import S3BackupConfig, S3BackupService
    report = tmp_path / "report.md"
    report.write_text("private report", encoding="utf-8")
    sent = {}
    class FakeClient:
        def __init__(self, _target): pass
        def upload_bytes(self, key, data): sent.update(key=key, data=data)
    monkeypatch.setattr("server.webdav_backup.S3Client", FakeClient)
    service = S3BackupService(str(tmp_path / "config.json"))
    service.upload_report_with_config(S3BackupConfig(endpoint="s3.example", bucket="bucket", secret_key="secret"), str(report), username="alice", user_id=7)
    assert "users/alice-7/reports/" in sent["key"]
    assert sent["data"] == b"private report"
