package com.mytimelogger.app;

import android.app.PendingIntent;
import static org.junit.Assert.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import org.junit.Test;

public class WidgetTimerCommandReceiverTest {
    private static Map<String, Object> raw(String id, long categoryId) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("action", "start"); value.put("commandId", id);
        value.put("categoryId", categoryId); value.put("eventEpochMs", 1000L); return value;
    }
    private static WidgetTimerCommand command(String id) { return WidgetTimerCommand.parse(raw(id, 2L)); }

    @Test public void commandContractBlocksOnlyStructuredCategories() {
        assertTrue(WidgetTimerCommand.isBlockedCategoryName("输入")); assertTrue(WidgetTimerCommand.isBlockedCategoryName("输出"));
        assertFalse(WidgetTimerCommand.isBlockedCategoryName("状态切换")); assertEquals("start", command("ordinary").action);
        assertThrows(IllegalArgumentException.class, () -> WidgetTimerCommand.parse(Collections.singletonMap("url", "x")));
    }

    @Test public void liveAckAndTimeoutRaceEachApplyExactlyOnce() {
        final int[] fallback = {0};
        WidgetCommandStore liveStore = new WidgetCommandStore(8);
        WidgetTimerCommandReceiver.LivePort live = new WidgetTimerCommandReceiver.LivePort() {
            public boolean dispatch(WidgetTimerCommand value) { return true; }
            public String awaitAck(String id) { return "applied"; }
        };
        assertEquals("applied", WidgetTimerCommandReceiver.coordinate(command("live"), liveStore, live, () -> { fallback[0]++; return "applied"; }));
        assertEquals(0, fallback[0]);

        WidgetCommandStore raceStore = new WidgetCommandStore(8);
        WidgetTimerCommandReceiver.LivePort late = new WidgetTimerCommandReceiver.LivePort() {
            public boolean dispatch(WidgetTimerCommand value) { return true; }
            public String awaitAck(String id) { raceStore.markApplied(id, "applied"); return null; }
        };
        assertEquals("applied", WidgetTimerCommandReceiver.coordinate(command("late"), raceStore, late, () -> { fallback[0]++; return "applied"; }));
        assertEquals(0, fallback[0]);

        WidgetCommandStore timeoutStore = new WidgetCommandStore(8);
        WidgetTimerCommandReceiver.LivePort slow = new WidgetTimerCommandReceiver.LivePort() {
            public boolean dispatch(WidgetTimerCommand value) { return true; } public String awaitAck(String id) { return null; }
        };
        assertEquals("applied", WidgetTimerCommandReceiver.coordinate(command("timeout"), timeoutStore, slow, () -> { fallback[0]++; return "applied"; }));
        assertEquals(1, fallback[0]);
        assertTrue(timeoutStore.get("timeout").applied);
    }

    @Test public void pendingIntentIsExplicitImmutableAndRejectsInjectedFields() {
        WidgetTimerCommandReceiver.PendingIntentSpec spec =
                WidgetTimerCommandReceiver.pendingIntentSpec("com.mytimelogger.app", command("secure"));
        assertEquals("com.mytimelogger.app", spec.packageName);
        assertEquals(WidgetTimerCommandReceiver.class.getName(), spec.componentClassName);
        assertEquals(PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE, spec.flags);
        assertEquals(spec.requestCode, WidgetTimerCommandReceiver.requestCode("secure"));
        assertEquals(new HashSet<>(Arrays.asList("action", "commandId", "categoryId", "eventEpochMs")),
                spec.extras.keySet());
        Map<String, Object> received = WidgetTimerCommandReceiver.receivedRaw(spec.extras, 9_999L);
        assertEquals(9_999L, received.get("eventEpochMs"));
        assertNotEquals(received.get("eventEpochMs"), spec.extras.get("eventEpochMs"));

        WidgetCommandStore store = new WidgetCommandStore(8);
        for (String injected : Arrays.asList("sql", "url", "path")) {
            Map<String, Object> evil = raw("evil-" + injected, 2L); evil.put(injected, "x");
            assertThrows(IllegalArgumentException.class, () -> WidgetTimerCommand.parse(evil));
            assertNull(store.get("evil-" + injected));
        }
    }

    @Test public void receiverRequiresAuthoritativeBridgeAndNeverWritesNativeTimerState() throws Exception {
        String source = new String(Files.readAllBytes(Paths.get("src", "main", "java", "com",
                "mytimelogger", "app", "WidgetTimerCommandReceiver.java")), StandardCharsets.UTF_8);
        for (String token : Arrays.asList("goAsync()", "WidgetTimerBridge.current()",
                "new WidgetTimerRepository(context)", "new WidgetCommandStore(backend",
                "new WidgetTimerRuntimeStore(context).read()", "new WidgetTimerApiClient().execute(",
                "WidgetTimerAuthoritativeSnapshotMapper.map(", "preferences.saveSnapshot(",
                ".setClass(app, TimerWidgetProvider.class)"))
            assertTrue(token, source.contains(token));
        for (String forbidden : Arrays.asList("saveSession(", "openTimerPage(", "openTimerPendingIntent(",
                "new WidgetIntegrationJournal(", "journal.append(command)",
                "WidgetTimerEngine.apply("))
            assertFalse(forbidden, source.contains(forbidden));
        assertFalse(source.contains("handler = command -> \"failed\""));
        String factory = new String(Files.readAllBytes(Paths.get("src", "main", "java", "com",
                "mytimelogger", "app", "TimerWidgetViewsFactory.java")), StandardCharsets.UTF_8);
        assertTrue(factory.contains("setOnClickFillInIntent(R.id.widget_category_icon, fillIn)"));
        assertTrue(factory.contains("setOnClickFillInIntent(R.id.widget_category_name, fillIn)"));
    }

    @Test public void persistentCommandStoreSurvivesRuntimeRestart() {
        Map<String, String> disk = new HashMap<>();
        WidgetTimerPreferences.Backend backend = new WidgetTimerPreferences.Backend() {
            public String get(String key) { return disk.get(key); }
            public void put(String key, String value) { disk.put(key, value); }
        };
        WidgetCommandStore first = new WidgetCommandStore(backend, 8);
        assertTrue(first.claim("restart-safe").newlyClaimed);
        first.markApplied("restart-safe", "applied");
        WidgetCommandStore restarted = new WidgetCommandStore(backend, 8);
        WidgetCommandStore.Entry replay = restarted.claim("restart-safe");
        assertFalse(replay.newlyClaimed);
        assertTrue(replay.applied);
        assertEquals("applied", replay.result);
    }

    @Test public void headlessFailuresNeverOverwriteLastSnapshot() {
        Map<String,String> disk=new HashMap<>(); WidgetTimerPreferences.Backend backend=new WidgetTimerPreferences.Backend(){public String get(String key){return disk.get(key);}public void put(String key,String value){disk.put(key,value);}};
        WidgetTimerPreferences preferences=new WidgetTimerPreferences(backend); String old=WidgetTimerAuthoritativeSnapshotMapper.map(WidgetTimerCurrentState.parse("{\"status\":\"stopped\",\"state\":null}"),1); assertTrue(preferences.saveSnapshot(old));
        for(String status:Arrays.asList("unauthorized","network","timeout")){WidgetCommandStore store=new WidgetCommandStore(8);String id="fail-"+status;store.claim(id);assertEquals("failed",WidgetTimerCommandReceiver.persistHeadless(new WidgetTimerApiClient.Outcome(status,null),preferences,store,id,2));assertEquals(old,preferences.loadSnapshot());assertFalse(store.get(id).applied);}
    }

    @Test public void refreshIsExplicitImmutableAndOnlySuccessReplacesSnapshot() {
        WidgetTimerCommandReceiver.PendingIntentSpec spec = WidgetTimerCommandReceiver.refreshPendingIntentSpec("com.mytimelogger.app");
        assertEquals("com.mytimelogger.app", spec.packageName);
        assertEquals(WidgetTimerCommandReceiver.class.getName(), spec.componentClassName);
        assertEquals(PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE, spec.flags);
        assertTrue(spec.extras.isEmpty());
        Map<String,String> disk=new HashMap<>(); WidgetTimerPreferences.Backend backend=new WidgetTimerPreferences.Backend(){public String get(String key){return disk.get(key);}public void put(String key,String value){disk.put(key,value);}};
        WidgetTimerPreferences preferences=new WidgetTimerPreferences(backend); String old=WidgetTimerAuthoritativeSnapshotMapper.map(WidgetTimerCurrentState.parse("{\"status\":\"stopped\",\"state\":null}"),1); assertTrue(preferences.saveSnapshot(old));
        assertFalse(WidgetTimerCommandReceiver.persistRefresh(new WidgetTimerApiClient.Outcome("network",null),preferences,2)); assertEquals(old,preferences.loadSnapshot());
        WidgetTimerCurrentState running=WidgetTimerCurrentState.parse("{\"status\":\"active\",\"state\":{\"session_id\":\"s1\",\"revision\":2,\"state\":\"running\",\"active\":true,\"category_id\":7,\"category_name\":\"运动\",\"started_at\":\"2026-09-07 10:00:00+08:00\",\"segment_started_at\":\"2026-09-07 10:00:00+08:00\",\"active_elapsed_ms\":1000,\"timer_mode\":\"countup\",\"duration_ms\":0,\"pause_count\":0,\"server_time\":\"2026-09-07 10:00:01+08:00\"}}");
        assertTrue(WidgetTimerCommandReceiver.persistRefresh(new WidgetTimerApiClient.Outcome("applied",running),preferences,2)); assertNotEquals(old,preferences.loadSnapshot());
    }

    @Test public void parsesCompleteNativeFallbackSnapshot() {
        String json = "{\"version\":1,\"capturedAtEpochMs\":1784494925704,\"state\":\"countup_studying\"," +
                "\"isPaused\":false,\"category\":{\"id\":3,\"name\":\"普通分类\",\"task\":\"\"}," +
                "\"pause\":{\"count\":0,\"reasons\":[],\"startedAtEpochMs\":null},\"segments\":[]," +
                "\"session\":{\"startedAtEpochMs\":1784494925704,\"largeStartedAtEpochMs\":1784494925704," +
                "\"durationSeconds\":0,\"totalStudySeconds\":0,\"currentCycleStudySeconds\":0," +
                "\"netDurationSeconds\":0},\"timing\":{\"mode\":\"countup\",\"elapsedMs\":0," +
                "\"deadlineEpochMs\":null}}";
        WidgetTimerSnapshotParser.Parsed parsed = WidgetTimerSnapshotParser.parse(json);
        assertNotNull(parsed);
        assertEquals("countup_studying", parsed.snapshot.state);
        assertEquals(Long.valueOf(3L), parsed.snapshot.categoryId);
    }
}
