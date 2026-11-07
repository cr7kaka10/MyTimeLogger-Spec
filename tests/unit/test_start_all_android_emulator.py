import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_android_log_contention_does_not_abort_startup_summary():
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(ROOT / "scripts" / "start-android-dev.ps1"), "-DryRun", "-TestScenario", "log_contention"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Startup log is temporarily locked" in result.stderr
    match = re.search(r"Summary: (.+\.summary\.json) \(success/dry_run\)", result.stdout)
    assert match, result.stdout
    summary = json.loads(Path(match.group(1)).read_text(encoding="utf-8-sig"))
    assert (summary["result"], summary["stage"], summary["exit_code"]) == ("success", "dry_run", 0)
    log = Path(summary["log_path"]).read_text(encoding="utf-8-sig")
    assert "Dry-run log contention recovered." in log


def test_start_all_orchestrates_android_without_destructive_operations():
    batch = (ROOT / "start-all.bat").read_text(encoding="utf-8").lower()
    helper = (ROOT / "scripts" / "start-android-dev.ps1").read_text(encoding="utf-8").lower()
    bounds = (ROOT / "scripts" / "ensure-window-visible.ps1").read_text(encoding="utf-8").lower()
    preflight = batch.index("start-android-dev.ps1\" -preflightonly")
    server = batch.index("start-local-process.ps1\" -name server")
    electron = batch.index("launching electron")
    android = batch.rindex("start-android-dev.ps1\"")
    assert preflight < server < electron < android
    assert "[switch]$dryrun" in helper
    assert "atimelogger_extraction_api35" in helper
    assert "emulator-5554" in helper
    assert "emu avd name" not in helper
    assert "wait-job -job $job -timeout 5" in helper
    assert helper.index("target avd process already exists") < helper.index("start-process -filepath $script:emulator")
    assert "npm run build:android-web" in helper
    assert "npx cap sync android" in helper
    assert "ui\\android\\gradlew.bat" in helper
    assert "$env:adb_server_port = '5038'" in helper
    assert ":app:assembledebug" in helper
    assert "& $script:adb -s $serial install -r $apkpath" in helper
    assert ":app:installdebug" not in helper
    assert "com.mytimelogger.app/.mainactivity" in helper
    assert "wait-androidinputready" in helper
    assert "focusedwindows" in helper
    assert "input_ready" in helper
    assert "$s.input_ready -eq $true" in batch
    assert "am force-stop com.mytimelogger.app" in helper
    assert "shell reboot" in helper
    assert "reverse tcp:8000 tcp:8000" in helper
    assert "reverse tcp:18010 tcp:8000" not in helper
    assert "reverse --remove tcp:18010" in helper
    assert "legacy http reverse tcp:18010 is already absent" in helper
    assert "get-ciminstance win32_process" in helper
    assert "-avd\\s+" in helper
    assert "qemu-system-x86_64.exe" in helper
    assert "wscript.shell" in bounds
    assert "appactivate" in bounds
    assert "request-targetemulatorforeground" in helper
    assert "function resolve-androidsdk" in helper
    assert "getenvironmentvariable('android_sdk_root', 'user')" in helper
    assert "getfolderpath([environment+specialfolder]::localapplicationdata)" in helper
    assert "test-path $script:adb" not in helper
    assert "test-path $script:emulator" not in helper
    assert "-not $script:adb -or -not (test-path -literalpath $script:adb -pathtype leaf)" in helper
    assert "-not $script:emulator -or -not (test-path -literalpath $script:emulator -pathtype leaf)" in helper
    assert "stop-process -id $confirmedpid -erroraction stop" in helper
    assert "stop-process -name" not in helper
    assert "kill" not in helper
    assert "wipe-data" not in helper
    assert "pm clear" not in helper
    assert "taskkill" not in helper


def test_start_all_attempts_both_clients_and_aggregates_results():
    batch = (ROOT / "start-all.bat").read_text(encoding="utf-8").lower()
    electron = batch.index("launching electron")
    android = batch.index("launching android development client")
    summary = batch.index("local startup summary")
    assert electron < android < summary
    assert "electron_exit=%errorlevel%" in batch
    assert "android_exit=%errorlevel%" in batch
    assert "server: ready" in batch and "vite: ready" in batch
    assert "pc: ready" in batch and "pc: failed" in batch
    assert "android: ready" in batch and "android: failed" in batch
    assert batch.index("if not \"%electron_exit%\"==\"0\"") > android
    assert batch.index("if not \"%android_exit%\"==\"0\"") > android
    assert "if not defined android_summary" in batch


def test_shared_dependency_failures_remain_fail_fast():
    batch = (ROOT / "start-all.bat").read_text(encoding="utf-8").lower()
    shared = batch[: batch.index("launching electron")]
    assert shared.count("if errorlevel 1 goto :failed") == 5
