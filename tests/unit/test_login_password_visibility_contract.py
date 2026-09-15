from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_login_password_visibility_and_401_diagnostic_contract():
    source = (ROOT / "ui" / "src" / "components" / "Auth" / "LoginPage.tsx").read_text(encoding="utf-8")
    assert "const [showPassword, setShowPassword] = useState(false)" in source
    assert "type={showPassword ? 'text' : 'password'}" in source
    assert "aria-label={showPassword ? '隐藏密码' : '显示密码'}" in source
    assert "setShowPassword(current => !current)" in source
    assert "formatAuthenticationFailure(result.error, base)" in source
    assert "HTTP 401" in source and "服务端：" in source
    assert "setConfig(" not in source and "localStorage" not in source
