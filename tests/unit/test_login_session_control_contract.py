from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_login_requires_server_validation_before_restoring_session():
    source = (ROOT / "server" / "templates" / "login.html").read_text(encoding="utf-8")
    assert "async function restoreSession()" in source
    assert "fetch('/auth/me'" in source
    assert "clearSession()" in source
    assert "restoreSession()" in source
    assert "showLoggedIn(savedUser" not in source


def test_logout_clears_all_account_scoped_browser_keys():
    source = (ROOT / "server" / "templates" / "login.html").read_text(encoding="utf-8")
    assert 'class="account-bar" id="account-bar"' in source
    assert 'class="logout" id="logout"' in source
    assert "$('account-bar').hidden = false" in source
    assert "key.startsWith('mtl_') || key.startsWith('sleep_')" in source
    assert "fetch('/auth/logout'" in source
    assert "finally {\n        clearSession()" in source
