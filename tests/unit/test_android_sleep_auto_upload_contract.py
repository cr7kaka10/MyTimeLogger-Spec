from pathlib import Path


SOURCE = (Path(__file__).parents[2] / "server" / "server.py").read_text(encoding="utf-8")
UPLOAD = SOURCE[SOURCE.index('@app.post("/upload")'):SOURCE.index('@app.get("/status/{request_id}")')]
STATUS = SOURCE[SOURCE.index('@app.get("/status/{request_id}")'):]


def test_android_auto_upload_is_authenticated_and_requests_fast_analysis():
    assert "user: dict = Depends(get_current_user_optional)" in UPLOAD
    assert "analyze: bool = True" in UPLOAD
    assert "full: bool = False" in UPLOAD
    assert "date: str | None = None" in UPLOAD
    assert 'background_tasks.add_task(_run_analysis' in UPLOAD


def test_android_auto_upload_reuses_completed_image_hash_only_for_same_date():
    assert 'store.get_done_job_by_image_hash(image_hash, user["id"])' in UPLOAD
    assert '"reused": True' in UPLOAD
    assert '"cache_reason": "image_hash"' in UPLOAD
    assert "cached_date != date" in UPLOAD
    assert '"error_code": "date_mismatch"' in UPLOAD


def test_android_auto_upload_persists_expected_date_and_request_id():
    assert "store.create_job(request_id, image_path, user_id=user[\"id\"], date=date" in UPLOAD
    assert 'return {"status": "ok", "request_id": request_id, "analyze": True}' in UPLOAD


def test_status_contract_is_user_scoped_and_exposes_terminal_states():
    route = STATUS[:STATUS.index("@app.", 1)]
    assert 'store.get_job(request_id, user_id=user["id"])' in route
    assert "public = _public_job(job)" in route
    public_job = SOURCE[SOURCE.index("def _public_job(job):"):SOURCE.index("def _cleanup_queue")]
    assert '"status": "done" if job.get("status") == "reused" else job.get("status")' in public_job
