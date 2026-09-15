from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_android_emulator_window_is_clamped_to_windows_working_area():
    bounds = (ROOT / "scripts" / "ensure-window-visible.ps1").read_text(encoding="utf-8").lower()
    android = (ROOT / "scripts" / "start-android-dev.ps1").read_text(encoding="utf-8").lower()
    assert "windowprocessid" in bounds and "get-process -id" in bounds
    assert "getwindowrect" in bounds and "workingarea" in bounds
    assert "[math]::min" in bounds and "movewindow" in bounds
    assert "setforegroundwindow" in bounds and "appactivate" in bounds
    assert "fullyvisible" in bounds and "before=" in bounds and "after=" in bounds
    assert "ensure-window-visible.ps1" in android
    assert "-windowprocessid $windowpid" in android
    assert "foreground_boot" in android and "window_visibility_failed" in bounds
    for forbidden in ("stop-process", "taskkill", "wipe-data", "adb emu kill"):
        assert forbidden not in bounds and forbidden not in android
