import importlib.util
import sqlite3
from pathlib import Path

from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema


MODULE_PATH = Path(__file__).resolve().parents[2] / "server" / "skills" / "time-management" / "generate_full_report.py"
spec = importlib.util.spec_from_file_location("generate_full_report_user_isolation_test", MODULE_PATH)
report_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(report_module)


def test_report_cache_and_paths_are_user_scoped(tmp_path, monkeypatch):
    path = tmp_path / "server.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'alice','x','x'),(2,'bob','x','x')")
    conn.commit(); conn.close()
    db = ServerDBWrapper(str(path))
    db.save_huawei_sleep_data(1, "2026-09-01", {"sleep_score": 61, "analysis_report": "alice"})
    db.save_huawei_sleep_data(2, "2026-09-01", {"sleep_score": 93, "analysis_report": "bob"})
    assert db.get_huawei_sleep_data(1, "2026-09-01")["sleep_score"] == 61
    assert db.get_huawei_sleep_data(2, "2026-09-01")["sleep_score"] == 93
    monkeypatch.setattr(report_module, "resolve_reports_dir", lambda user_id=None: tmp_path / (f"user-{user_id}" if user_id else "legacy"))
    one = Path(report_module.generate_report_filename("2026-09-01", user_id=1))
    two = Path(report_module.generate_report_filename("2026-09-01", user_id=2))
    assert one != two and one.parent.name == "user-1" and two.parent.name == "user-2"
