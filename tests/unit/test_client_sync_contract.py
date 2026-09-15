# -*- coding: utf-8 -*-
import os


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(path: str) -> str:
    with open(os.path.join(ROOT_DIR, path), "r", encoding="utf-8") as f:
        return f.read()


def test_checklist_coin_operations_use_fast_task_mutation_sync():
    src = _read("ui/src/hooks/useChecklist.ts")
    db = _read("core/models/Database.ts")
    legacy_page = _read("ui/src/components/Checklist/ChecklistPage.tsx")
    unified_page = _read("ui/src/pages/UnifiedChecklistPage/TaskSection.tsx")

    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-complete' })" in src
    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-delete' })" in src
    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-priority' })" in src
    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-add' })" in src
    assert "checklist-task-fail" not in src
    assert "failTask" not in src
    assert "failTask" not in db
    assert "status=4" not in db
    assert "status = 4" not in db
    assert "handleFail" not in legacy_page
    assert "handleFail" not in unified_page
    assert "reason: forceRefresh ? 'checklist-refresh' : 'checklist-enter'" in src
    assert "refreshTickTick: false" in src
    assert "const shouldRefreshProvider = forceRefresh || isStaleSyncTime" in src
    assert "refreshTickTick: shouldRefreshProvider" in src


def test_habit_checkins_use_forced_ticktick_sync():
    src = _read("ui/src/hooks/useHabits.ts")

    assert "syncNow({ refreshTickTick: true, reason: 'habit-checkin' })" in src


def test_forced_refresh_keeps_version_cursor_and_runs_provider_reconcile():
    src = _read("core/core/SyncWorker.ts")
    server = _read("server/server.py")
    api = _read("core/core/ApiClient.ts")
    sync_config = _read("core/core/SyncConfig.ts")

    assert "if (lastSync && !refresh) params.since = lastSync" in src
    assert "diagnostics = await sync_hub.force_pull_ticktick(user_id=user[\"id\"], request_id=request_id)" in server
    assert "self._provider_reconcile_tasks: dict[int, asyncio.Task] = {}" in _read("server/sync_hub.py")
    assert "return { ok: false, merged, diagnostics" in src
    assert "return { ok: false, merged: 0, diagnostics" not in src
    assert "refresh: 45_000" in sync_config
    assert "refresh ? SYNC_CONFIG.timeout.refresh : undefined" in src
    assert "SYNC_CONFIG.timeout.default" in api


def test_checklist_refresh_status_surfaces_diagnostics():
    src = _read("ui/src/hooks/useChecklist.ts")
    server = _read("server/sync_hub.py")

    assert "formatSyncDiagnostics" in src
    assert "任务 新${activeTasks}/完${completedTasks}" in src
    assert "同步失败 · ${formatSyncDiagnostics(result)}" in src
    assert "foreground" in server
    assert "merged_count" in server
    assert "started_at" in server
    assert "finished_at" in server


def test_ticktick_pull_does_not_touch_unchanged_task_updated_at():
    wrapper = _read("server/db_wrapper.py")
    hub = _read("server/sync_hub.py")

    assert "if unchanged:" in wrapper
    assert "return False" in wrapper
    assert "return True" in wrapper
    assert "active_task_changes" in hub
    assert "completed_task_changes" in hub
    assert "changed = self.db.upsert_task" in hub


def test_ticktick_provider_pull_reuses_delta_classifier_for_all_records():
    hub = _read("server/sync_hub.py")
    assert ".provider_delta_filter import" in hub
    assert "classify_provider_records" in hub
    assert hub.count("classify_provider_records(") >= 4
    assert '"etag": t.get("etag", "")' in hub
    assert 'source_checkin.get("opTime")' in hub
    assert "MissingProviderFingerprintError" in hub
    assert "缺少增量指纹" in hub


def test_provider_tables_do_not_use_source_hash():
    schema = _read("server/models/server_schema.py")
    wrapper = _read("server/db_wrapper.py")
    assert "source_hash" not in schema
    assert "source_hash" not in wrapper


def test_checklist_dates_use_shanghai_timezone_helper():
    hook = _read("ui/src/hooks/useChecklist.ts")
    section = _read("ui/src/pages/UnifiedChecklistPage/TaskSection.tsx")
    calendar = _read("ui/src/pages/UnifiedChecklistPage/WeekCalendar.tsx")

    assert "formatTickTickDueDate" in hook
    assert "tickTickDateToShanghaiDateString" in section
    assert "tickTickDateToShanghaiDateString" in calendar


def test_directional_sync_watermarks_are_declared_with_chinese_comments():
    client_schema = _read("core/models/Schema.ts")
    server_schema = _read("server/models/server_schema.py")

    for key, comment in [
        ("client_to_server_synced_at", "客户端往服务端同步时间"),
        ("server_to_client_synced_at", "服务端往客户端同步时间"),
        ("server_to_ticktick_synced_at", "服务端往滴答清单同步时间"),
        ("ticktick_to_server_synced_at", "滴答清单往服务端同步时间"),
    ]:
        assert key in client_schema
        assert comment in client_schema

    assert "CREATE TABLE IF NOT EXISTS server_sync_state" in server_schema
    for comment in [
        "同步系统（client/ticktick）",
        "同步方向（client_to_server/server_to_client/server_to_ticktick/ticktick_to_server）",
        "最后成功同步时间（北京时间）",
        "最后尝试同步时间（北京时间）",
        "最后合并记录数",
    ]:
        assert comment in server_schema

    assert "是否归档（1归档,0未归档，正常显示）" in client_schema
    assert "是否归档（1归档,0未归档，正常显示）" in server_schema
    assert "UPDATE sqlite_master SET sql = replace(sql, '是否归档标记(1启用,0禁用)', '是否归档（1归档,0未归档，正常显示）')" in client_schema
    assert "UPDATE sqlite_master SET sql = replace(sql, '软删除标记(1启用,0禁用)', '是否归档（1归档,0未归档，正常显示）')" in client_schema
    assert "是否激活（1=是,0=否）" in server_schema
    assert "WHERE type='table' AND name='server_habits'" in server_schema


def test_client_push_and_pull_use_separate_watermarks():
    src = _read("core/core/SyncWorker.ts")

    assert "setConfig('client_to_server_synced_at', serverTime)" in src
    assert "getConfig('server_to_client_synced_at') || this._db.getConfig('last_sync_at')" in src
    assert "setConfig('server_to_client_synced_at', serverTime)" in src
    assert "setConfig('server_to_ticktick_synced_at'" in src
    assert "setConfig('ticktick_to_server_synced_at'" in src


def test_client_declares_dedicated_version_sync_state():
    schema = _read("core/models/Schema.ts")
    db = _read("core/models/Database.ts")

    assert "CREATE TABLE IF NOT EXISTS client_sync_state" in schema
    assert "last_server_version" in schema
    assert "客户端最后成功应用的服务端版本号" in schema
    assert "getLastServerVersion()" in db
    assert "setLastServerVersion(version: number)" in db
    assert "runInTransaction(fn: () => void)" in db
    assert "ROLLBACK" in db
    assert "ON CONFLICT(key) DO UPDATE" in db


def test_sync_worker_prefers_since_version_when_available():
    src = _read("core/core/SyncWorker.ts")

    assert "getLastServerVersion" in src
    assert "params.since_version = String(lastServerVersion)" in src
    assert "else if (lastSync && !refresh) params.since = lastSync" in src
    assert "sync_protocol') === 'legacy_timestamp'" in src
    assert "setLastServerVersion?.(resp.data.to_version)" in src
    assert "runInTransaction(applySyncState)" in src
    assert "const versionChanges = Array.isArray(resp.data.changes)" in src


def test_sync_regression_suite_clickable_entrypoints_exist():
    ps1 = _read("scripts/sync-regression-suite.ps1")
    py = _read("scripts/sync-regression-suite.py")

    assert "sync-regression-suite.py" in ps1
    assert "FakeTickTickClient" in py
    assert "sync-regression-report.md" in py
    assert "任务-更新截止时间" in py
    assert "习惯-失败打卡" in py


def test_client_outbox_contract_is_durable_and_task_actions_write_it():
    schema = _read("core/models/Schema.ts")
    db = _read("core/models/Database.ts")

    assert "CREATE TABLE IF NOT EXISTS sync_outbox" in schema
    for column in [
        "change_id TEXT NOT NULL UNIQUE",
        "device_id TEXT NOT NULL",
        "table_name TEXT NOT NULL",
        "record_id TEXT NOT NULL",
        "operation TEXT NOT NULL",
        "base_version TEXT",
        "payload_json TEXT NOT NULL",
        "retry_count INTEGER NOT NULL DEFAULT 0",
        "last_error TEXT",
    ]:
        assert column in schema

    assert "ensureDeviceId()" in db
    assert "this.setConfig('device_id', deviceId, '客户端设备 ID')" in db
    assert "createOutboxOperation(" in db
    assert "getPendingOutbox" in db
    assert "markOutboxSynced" in db
    assert "markOutboxFailed" in db
    assert "this._enqueueOutbox(table, id, 'upsert'" in db
    assert "this._enqueueOutbox('tasks', id, 'delete'" in db


def test_outbox_push_uses_per_operation_results():
    worker = _read("core/core/SyncWorker.ts")
    server = _read("server/server.py")
    hub = _read("server/sync_hub.py")

    assert "operation_results" in server
    assert "operation_results: list[dict] = []" in hub
    assert '"status": "accepted"' in hub
    assert '"status": "rejected"' in hub
    assert '"status": "duplicate"' in hub
    assert "const results = Array.isArray(resp.data.operation_results)" in worker
    assert "markOutboxSynced?.(acceptedIds, serverTime)" in worker
    assert "markOutboxFailed?.([item.id], item.reason)" in worker


def test_sync_worker_start_pushes_before_initial_pull():
    worker = _read("core/core/SyncWorker.ts")

    assert "this.flushNow(false, this._createContext('worker-startup')).catch" in worker
    assert "startup push/pull failed" in worker


def test_checklist_mutations_trigger_immediate_sync_and_show_diagnostics():
    hook = _read("ui/src/hooks/useChecklist.ts")
    page = _read("ui/src/pages/UnifiedChecklistPage/index.tsx")

    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-add' })" in hook
    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-complete' })" in hook
    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-delete' })" in hook
    assert "syncNow({ refreshTickTick: false, reason: 'checklist-task-priority' })" in hook
    assert "provider_refresh" in hook
    assert "diagnostics.protocol" in hook
    assert "{checklist.syncStatus} · {checklist.tasks.length}任务" in page
    assert "checklist.refreshFromTickTick(true)" in page


def test_refresh_pull_keeps_version_cursor_and_can_request_provider_refresh():
    worker = _read("core/core/SyncWorker.ts")

    assert "const useVersionPull = !forceLegacySync && typeof lastServerVersion === 'number' && lastServerVersion >= 0" in worker
    assert "if (useVersionPull) params.since_version = String(lastServerVersion)" in worker
    assert "if (refresh) params.refresh = 'true'" in worker
    assert "const useVersionPull = !forceLegacySync && typeof lastServerVersion === 'number' && lastServerVersion >= 0 && !refresh" not in worker


def test_server_records_four_directional_watermarks():
    src = _read("server/sync_hub.py")
    api = _read("server/server.py")

    assert "def _record_sync_state(" in src
    assert '"client", "client_to_server"' in src
    assert '"client", "server_to_client"' in src
    assert '"ticktick", "server_to_ticktick"' in src
    assert '"ticktick", "ticktick_to_server"' in src
    assert '"sync_state": result.get("sync_state")' in api


def test_sync_chain_logs_request_id_and_never_logs_token_values():
    db = _read("ui/src/db.ts")
    api = _read("core/core/ApiClient.ts")
    worker = _read("core/core/SyncWorker.ts")
    server = _read("server/server.py")
    hub = _read("server/sync_hub.py")
    ticktick = _read("server/ticktick_client.py")

    assert "createSyncRunId" in db
    assert "_syncWorker.flushNow(refresh, { syncRunId, reason })" in db
    assert "'X-Sync-Run-Id'" in api
    assert "token_present" in api
    assert "token_length" in api
    assert "console.info('[SyncWorker] pull start'" in worker
    assert "console.warn('[SyncWorker] pull failed'" in worker
    assert "request.headers.get(\"x-sync-run-id\")" in server
    assert "\"request_id\": request_id" in server
    assert "[SyncHub] version pull start" in hub
    assert "[ProviderReconcile] tasks start" in hub
    assert "[TickTickClient] request start" in ticktick

    request_start_block = api.split("console.info('[ApiClient] request start'", 1)[1].split("})", 1)[0]
    assert "authToken:" not in request_start_block
    assert "Authorization" not in request_start_block


def test_background_sync_paths_have_request_ids_and_checklist_status_is_latest_only():
    worker = _read("core/core/SyncWorker.ts")
    hook = _read("ui/src/hooks/useChecklist.ts")

    assert "private _createContext(reason: string): SyncRunContext" in worker
    assert "this.pullAndMerge(false, this._createContext('sse-changed'))" in worker
    assert "this.pullAndMerge(false, this._createContext('config-change'))" in worker
    assert "this.flushNow(false, this._createContext('worker-startup'))" in worker
    assert "SYNC_CONFIG.api.push" in worker
    assert "SYNC_CONFIG.api.pull" in worker

    assert "const syncSeqRef = useRef(0)" in hook
    assert "const beginSyncStatus = useCallback" in hook
    assert "const setLatestSyncStatus = useCallback" in hook
    assert "ignore stale sync status" in hook
    assert "syncNow({ reason: 'checklist-startup' })" not in hook


def test_checklist_foreground_refresh_waits_for_provider_reconcile():
    hook = _read("ui/src/hooks/useChecklist.ts")

    assert "const shouldRefreshProvider = forceRefresh || isStaleSyncTime" in hook
    assert "refreshTickTick: shouldRefreshProvider" in hook
    assert "reason: forceRefresh ? 'checklist-refresh' : 'checklist-enter'" in hook
    assert "let providerReconcileInFlight: Promise<void> | null = null" not in hook
    assert "provider reconcile background failed" not in hook
    assert "provider reconcile skipped: in flight" not in hook


def test_checklist_reloads_after_background_pull_complete():
    worker = _read("core/core/SyncWorker.ts")
    hook = _read("ui/src/hooks/useChecklist.ts")

    assert "new w.CustomEvent('sync-pull-complete')" in worker
    assert "window.addEventListener('sync-pull-complete', handleSyncPullComplete)" in hook
    assert "sync-pull-complete: reload local tasks" in hook
    assert "后台更新" in hook
    assert "window.removeEventListener('sync-pull-complete', handleSyncPullComplete)" in hook


def test_checklist_foreground_pull_and_electron_renderer_logs_are_enabled():
    hook = _read("ui/src/hooks/useChecklist.ts")
    main = _read("desktop/main.js")

    assert "pullServerChanges" in hook
    assert "checklist.refreshFromTickTick(true)" in _read("ui/src/pages/UnifiedChecklistPage/index.tsx")
    assert "checklist-visible" in hook
    assert "checklist-focus" in hook
    assert "backgroundThrottling: false" in main
    assert "mainWindow.webContents.on('console-message'" in main
    assert "[Renderer:${label}]" in main


def test_reward_ledger_delete_tombstone_and_wallet_table_are_merged():
    worker = _read("core/core/SyncWorker.ts")
    schema = _read("core/models/Schema.ts")
    server_hub = _read("server/sync_hub.py")
    server_api = _read("server/server.py")

    assert "'user_wallets'" in worker
    assert "CREATE TABLE IF NOT EXISTS user_wallets" in schema
    assert "operation === 'delete'" in worker
    assert "DELETE FROM ${table} WHERE ${pk} = ?" in worker
    assert "table === 'user_wallets' && row.balance !== undefined" in worker
    assert '"wallet": result.get("wallet")' in server_api
    assert "\"_sync_operation\": \"delete\"" in server_hub
    assert "\"user_wallets\"" in server_hub


def test_checklist_entry_uses_refresh_button_sync_semantics():
    page = _read("ui/src/pages/UnifiedChecklistPage/index.tsx")
    hook = _read("ui/src/hooks/useChecklist.ts")

    assert "checklist.refreshFromTickTick(true)" in page
    assert "refreshTickTick: shouldRefreshProvider" in hook
    assert "scheduleProviderReconcile" not in hook


def test_ticktick_provider_pull_keeps_date_boundaries_and_local_filtering():
    hub = _read("server/sync_hub.py")
    ticktick = _read("server/ticktick_client.py")

    assert 'utc_start = "2026-05-31T16:00:00+0000"' in hub
    assert 'week_start = "20260601"' in hub
    assert '"from": from_stamp' in ticktick
    assert 'due_date and due_date < "2026-06-01 00:00:00" and tid not in db_known_tids' in hub
    assert 'delta.unchanged' in hub
