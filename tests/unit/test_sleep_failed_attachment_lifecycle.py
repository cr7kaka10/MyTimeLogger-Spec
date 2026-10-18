from pathlib import Path

import server.server as api
from server.store import ServerSleepStore


def test_failed_sleep_image_is_retained_for_72_hours_then_cleaned(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ATTACHMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_set_job_image_path", lambda *_: None)
    source = tmp_path / "request_image.jpg"
    source.write_bytes(b"image")
    retained = Path(api._retain_failed_sleep_image(str(source), "a" * 32, 7, now_ts=1000))
    assert retained.exists() and retained.name == f"failed_7_{'a' * 32}_{1000 + 72 * 60 * 60}.jpg"
    assert api._cleanup_expired_failed_sleep_images(now_ts=1000 + 71 * 60 * 60) == 0
    assert retained.exists()
    assert api._cleanup_expired_failed_sleep_images(now_ts=1000 + 72 * 60 * 60) == 1
    assert not retained.exists()


def test_failed_attachment_cleanup_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ATTACHMENTS_DIR", str(tmp_path))
    assert api._cleanup_expired_failed_sleep_images(now_ts=9999) == 0


def test_first_valid_upload_projection_never_moves_later(tmp_path):
    store = ServerSleepStore(db_path=str(tmp_path / "store.db"))
    user_id = store.create_user("upload_projection", "password123")
    store.record_valid_sleep_upload(user_id, "2026-10-03", "2026-10-03 16:29:10")
    store.record_valid_sleep_upload(user_id, "2026-10-03", "2026-10-03 16:31:00")
    store.record_valid_sleep_upload(user_id, "2026-10-03", "2026-10-03 08:59:00")
    assert store.get_huawei_sleep_data(user_id, "2026-10-03")["image_uploaded_at"] == "2026-10-03 08:59:00"


def test_successful_retry_removes_failed_attachment_path(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ATTACHMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_set_job_image_path", lambda *_: None)
    source = tmp_path / "request.jpg"
    source.write_bytes(b"image")
    retained = Path(api._retain_failed_sleep_image(str(source), "b" * 32, 8, now_ts=1000))
    archived = Path(api._archive_sleep_image(str(retained), "2026-10-03", "b" * 32, 8))
    assert not retained.exists()
    assert archived.name == "sleep_2026-10-03.jpg" and archived.exists()
    assert api._cleanup_expired_failed_sleep_images(now_ts=9999) == 0
