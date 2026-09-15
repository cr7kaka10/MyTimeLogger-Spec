from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_batch_uses_hidden_process_helper_and_keeps_startup_order():
    batch = (ROOT / "start-all.bat").read_text(encoding="utf-8").lower()
    helper = (ROOT / "scripts" / "start-local-process.ps1").read_text(encoding="utf-8").lower()
    readiness = (ROOT / "scripts" / "wait-local-readiness.ps1").read_text(encoding="utf-8").lower()
    assert "start \"mytimelogger server\"" not in batch
    assert "start \"mytimelogger ui\"" not in batch
    assert "start \"mytimelogger desktop\"" not in batch
    assert "start-local-process.ps1" in batch
    assert "-windowstyle hidden" in helper
    assert "-redirectstandardoutput" in helper
    assert "-redirectstandarderror" in helper
    assert "-passthru" in helper
    assert "python -m uvicorn" in helper
    assert "npm run dev" in helper
    assert "npm start" in helper
    assert "-requireportsfree" not in batch
    assert "mtl_start_all_noninteractive" in batch
    assert "pause" in batch
    assert "get-nettcpconnection" in helper
    assert "owningprocess" in helper
    assert "restarting verified" in helper
    assert "/ping" in helper and "http://127.0.0.1:5173/" in readiness
    assert "build_revision" in helper
    assert "get-ciminstance win32_process" in helper
    assert "refusing to stop it" in helper
    assert "stop-process -id $ownerpid" in helper
    assert "stop-process -name" not in helper
    assert "taskkill" not in helper

    assert "atimelogger_final_backup.version" in readiness
    assert "build_revision" in readiness


def test_electron_owns_single_instance_before_desktop_resources():
    main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8")
    lock = main.index("app.requestSingleInstanceLock()")
    ready = main.index("app.on('ready'")
    assert lock < ready
    assert "if (!gotTheLock)" in main
    assert "app.quit();" in main[lock:ready]
    assert "app.on('second-instance'" in main
    assert "app.whenReady().then(showMainWindow)" in main


def test_tray_left_click_is_an_idempotent_show_action():
    main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8")
    tray_click = main[main.index("tray.on('click'"):main.index("tray.on('right-click'")]
    assert "showMainWindow();" in tray_click
    assert "mainWindow.hide()" not in tray_click
    assert "mainWindow.isVisible()" not in tray_click
    assert "mainWindow.hide()" in main[:main.index("function createTray()")]
