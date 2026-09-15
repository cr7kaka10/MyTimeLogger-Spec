# -*- coding: utf-8 -*-
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from server.security_utils import hash_bearer_token, redact_mapping, redact_timer_lease_event
from server.store import ServerSleepStore


def _run_preflight_fixture(tmp_path, email, relative_path="tests/fixture.py"):
    root = tmp_path / "repo"
    (root / "deploy").mkdir(parents=True)
    (root / "tests").mkdir()
    script = Path(__file__).parents[2] / "deploy" / "security-preflight.ps1"
    (root / "deploy" / "security-preflight.ps1").write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
    fixture = root / relative_path
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(f"USER = '{email}'\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True, text=True)
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(root / "deploy" / "security-preflight.ps1"), "-Environment", "testing",
         "-RepositoryRoot", str(root)],
        capture_output=True, text=True, timeout=20,
    )


def test_security_preflight_handles_reserved_test_email_domains(tmp_path):
    allowed = _run_preflight_fixture(tmp_path / "allowed", "owner@example.test")
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr

    rejected = _run_preflight_fixture(tmp_path / "rejected", "owner@personal.test")
    assert rejected.returncode != 0
    assert "rule=personal-account" in rejected.stdout


def test_security_preflight_distinguishes_ui_contract_fixtures_from_runtime_data(tmp_path):
    ui_fixture = _run_preflight_fixture(tmp_path / "ui", "owner@example.test", "ui/tests/runtime/fixture.py")
    assert ui_fixture.returncode == 0, ui_fixture.stdout + ui_fixture.stderr

    runtime_fixture = _run_preflight_fixture(tmp_path / "runtime", "owner@example.test", "tests/runtime/result.json")
    assert runtime_fixture.returncode != 0
    assert "rule=personal-runtime" in runtime_fixture.stdout


def test_session_token_is_stored_as_hash_and_can_be_revoked(tmp_path):
    db_path = str(tmp_path / "server.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("family", "pass123")
    user_id = store.verify_user("family", "pass123")

    token = store.create_session(user_id)

    conn = sqlite3.connect(db_path)
    try:
        stored, expires_at = conn.execute("SELECT token, expires_at FROM sessions").fetchone()
    finally:
        conn.close()

    assert stored == hash_bearer_token(token)
    assert stored != token
    assert expires_at is None
    assert store.get_user_by_session(token)["username"] == "family"

    store.revoke_session(token)
    assert store.get_user_by_session(token) is None


def test_expired_session_cleanup_keeps_valid_sessions(tmp_path):
    db_path = str(tmp_path / "server.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("family", "pass123")
    user_id = store.verify_user("family", "pass123")
    valid_token = store.create_session(user_id)
    expired_token = "expired-token"
    expired_hash = hash_bearer_token(expired_token)
    expired_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (expired_hash, user_id, expired_at, expired_at),
        )
        conn.commit()
    finally:
        conn.close()

    assert store.get_user_by_session(expired_token) is None
    store.cleanup_expired_sessions()
    assert store.get_user_by_session(valid_token)["username"] == "family"

    conn = sqlite3.connect(db_path)
    try:
        remaining = [row[0] for row in conn.execute("SELECT token FROM sessions").fetchall()]
    finally:
        conn.close()

    assert hash_bearer_token(valid_token) in remaining
    assert expired_hash not in remaining


def test_redact_mapping_keeps_status_bools_and_masks_strings():
    result = redact_mapping({
        "secret_configured": True,
        "access_token": "abcdef123456",
        "nested": {"password": "passw0rd"},
    })

    assert result["secret_configured"] is True
    assert result["access_token"] == "abcd...3456"
    assert result["nested"]["password"] == "********"


def test_timer_lease_event_is_allowlisted_and_excludes_sensitive_payloads():
    result = redact_timer_lease_event({
        "user": 7,
        "session": "session-1",
        "revision": 3,
        "result": "conflict",
        "errorCode": "active_timer_conflict",
        "Authorization": "Bearer secret",
        "token": "secret",
        "note": "设备备注",
        "snapshot": {"category_name": "输入"},
        "activityId": "atm-1",
    })
    assert result == {
        "user": 7,
        "session": "session-1",
        "revision": 3,
        "result": "conflict",
        "errorCode": "active_timer_conflict",
    }


def test_private_env_loader_masks_sensitive_output(tmp_path):
    env_file = tmp_path / "config.development.local.env"
    env_file.write_text(
        "\n".join([
            "MTL_SERVER_URL=http://127.0.0.1:8000",
            "MTL_USERNAME=family",
            "TICKTICK_ACCESS_TOKEN=ticktick-secret-token",
            "S3_ENDPOINT=s3.example",
            "S3_SECRET_ACCESS_KEY=s3-secret-value",
            "ATIMELOGGER_PASSWORD=atimelogger-secret",
            "TEXT_API_KEY=text-secret-value",
            "TEXT_MODEL=glm-test",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "deploy/load-private-env.ps1",
            "-Environment",
            "development",
            "-ConfigPath",
            str(env_file),
        ],
        cwd="D:\\WorkSpace\\MyTimeLogger-Spec",
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "ticktick-secret-token" not in output
    assert "s3-secret-value" not in output
    assert "atimelogger-secret" not in output
    assert "text-secret-value" not in output
