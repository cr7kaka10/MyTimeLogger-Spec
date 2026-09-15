from pathlib import Path


def test_config_page_exposes_manual_s3_backup_without_rendering_credentials_in_status():
    page = (Path(__file__).resolve().parents[2] / "server" / "templates" / "config.html").read_text(encoding="utf-8")

    assert 'id="s3BackupNowBtn"' in page
    assert 'id="s3BackupStatus"' in page
    assert '"/admin/s3-backup/status"' in page
    assert '"/admin/s3-backup/run"' in page
    assert 'method: "POST"' in page
    assert 'CERTIFICATE_VERIFY_FAILED' in page
    assert 's3BackupStatus.textContent' in page
    assert 's3AccessKey' not in page[page.index("function showS3BackupStatus"):page.index("function applyConfig")]
