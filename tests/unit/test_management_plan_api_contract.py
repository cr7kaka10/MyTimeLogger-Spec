from server.server import app


def test_management_plan_api_contract_is_stable_and_language_neutral():
    paths = app.openapi()["paths"]
    expected = {
        ("/api/management-plans/drafts", "post"),
        ("/api/management-plans/drafts/{draft_id}/preview", "post"),
        ("/api/management-plans/drafts/{draft_id}/apply", "post"),
        ("/api/management-plans/revisions", "get"),
        ("/api/management-plans/mindmap", "get"),
        ("/api/management-plans/revisions/{revision_id}/export", "get"),
        ("/api/management-plans/import/preview", "post"),
        ("/api/management-plans/import/apply", "post"),
        ("/api/management-plans/revisions/{revision_id}/patch/preview", "post"),
        ("/api/management-plans/revisions/compare", "get"),
    }
    assert {(path, method) for path, spec in paths.items() for method in spec if method in {"get", "post"}} >= expected
