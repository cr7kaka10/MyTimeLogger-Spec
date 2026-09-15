from pathlib import Path
import re


ROOT = Path(__file__).parents[2]
DEPLOY_TEST = (ROOT / "deploy" / "deploy-test.bat").read_text(encoding="utf-8")
ANDROID_BUILD = (ROOT / "deploy" / "build-android.ps1").read_text(encoding="utf-8")


def test_android_menu_uses_debug_build_entrypoint_and_stable_output():
    assert "[1]  Deploy ALL (Server + Desktop EXE + Android APK)" in DEPLOY_TEST
    assert "[4]  Android APK" in DEPLOY_TEST
    assert "build-android.ps1" in DEPLOY_TEST
    assert "MyTimeLogger-debug.apk" in ANDROID_BUILD
    assert "assembleDebug" in ANDROID_BUILD


def test_deploy_failure_contract_is_explicit_and_bounded():
    assert "HTTP_FAILED" in DEPLOY_TEST
    assert "SSH_ATTEMPTS" in DEPLOY_TEST
    assert "geq 3" in DEPLOY_TEST.lower()
    assert "[FAIL] Task failed" in DEPLOY_TEST


def test_android_build_does_not_install_or_start_a_device():
    assert "installDebug" not in ANDROID_BUILD
    assert "adb" not in ANDROID_BUILD.lower()


def _label_block(label, next_label):
    match = re.search(
        rf"(?ms)^:{label}\s*$\r?\n(.*?)(?=^:{next_label}\s*$)",
        DEPLOY_TEST,
    )
    assert match, f"missing batch label block: {label}"
    return match.group(1)


def _deploy_all_block():
    return _label_block("deploy_all", "run_server")


def test_full_deploy_runs_server_desktop_then_android_and_only_reports_success_last():
    block = _deploy_all_block()
    server_index = block.index("call :do_deploy_server")
    desktop_index = block.index("call :do_build_desktop")
    android_index = block.index("build-android.ps1")
    success_index = block.index("[OK] Full deployment completed!")
    assert server_index < desktop_index < android_index < success_index
    assert re.search(
        r'powershell[^\r\n]+build-android\.ps1[\s\S]+?if errorlevel 1[\s\S]+?\[FAIL\] Android APK build failed\.[\s\S]+?goto :failed',
        block,
    )


def test_full_deploy_failure_guards_short_circuit_later_stages():
    block = _deploy_all_block()
    server_guard = block.index("[FAIL] Server deploy failed")
    desktop_call = block.index("call :do_build_desktop")
    desktop_guard = block.index("[FAIL] Desktop build failed")
    android_call = block.index("build-android.ps1")
    assert server_guard < desktop_call
    assert desktop_guard < android_call
    assert "[FAIL] Android APK build failed" in block


def test_single_stage_menu_entries_remain_independent():
    assert 'if "%choice%"=="2" goto :run_server' in DEPLOY_TEST
    assert 'if "%choice%"=="3" goto :run_desktop' in DEPLOY_TEST
    assert 'if "%choice%"=="4" goto :run_android' in DEPLOY_TEST
    run_android = _label_block("run_android", "do_deploy_server")
    assert run_android.count("build-android.ps1") == 1
