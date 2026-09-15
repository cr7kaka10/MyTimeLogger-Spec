package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class WidgetTimerEngineTest {
    private static WidgetTimerCommand command(String action, long categoryId, long at) {
        Map<String, Object> value = new HashMap<>();
        value.put("action", action); value.put("commandId", "cmd-1");
        value.put("categoryId", categoryId); value.put("eventEpochMs", at);
        return WidgetTimerCommand.parse(value);
    }

    @Test public void ordinaryStartMatchesTypeScriptBoundary() {
        WidgetTimerEngine.Snapshot before = WidgetTimerEngine.Snapshot.stopped(100L);
        WidgetTimerEngine.Result result = WidgetTimerEngine.apply(before, command("start", 7L, 1000L), new WidgetTimerEngine.Category(7L, "副业研发", true));
        assertEquals("applied", result.status);
        assertEquals("countup_studying", result.snapshot.state);
        assertEquals(Long.valueOf(7L), result.snapshot.categoryId);
        assertEquals(1000L, result.snapshot.capturedAtEpochMs);
        assertEquals(Long.valueOf(1000L), result.snapshot.startedAtEpochMs);
    }

    @Test public void structuredOrBlockedTargetRequiresAppWithoutMutation() {
        WidgetTimerEngine.Snapshot stopped = WidgetTimerEngine.Snapshot.stopped(100L);
        WidgetTimerEngine.Result blocked = WidgetTimerEngine.apply(stopped, command("start", 7L, 1000L), new WidgetTimerEngine.Category(7L, "输入", true));
        assertEquals("requires_app", blocked.status); assertSame(stopped, blocked.snapshot);
        WidgetTimerEngine.Snapshot structured = new WidgetTimerEngine.Snapshot("studying", false, 7L, "输入", 100L, 0L, 100L);
        WidgetTimerEngine.Result active = WidgetTimerEngine.apply(structured, command("start", 8L, 1000L), new WidgetTimerEngine.Category(8L, "吃饭", true));
        assertEquals("requires_app", active.status); assertSame(structured, active.snapshot);
    }

    private static WidgetTimerEngine.Snapshot running() {
        return WidgetTimerEngine.apply(WidgetTimerEngine.Snapshot.stopped(100L), command("start", 7L, 1000L),
                new WidgetTimerEngine.Category(7L, "副业研发", true)).snapshot;
    }

    @Test public void sameCategoryAndReplayAreNoOps() {
        WidgetTimerEngine.Snapshot before = running();
        WidgetTimerEngine.Result same = WidgetTimerEngine.apply(before, command("switch", 7L, 4500L), new WidgetTimerEngine.Category(7L, "副业研发", true));
        assertEquals("noop", same.status); assertSame(before, same.snapshot); assertTrue(same.sessions.isEmpty());
        WidgetTimerEngine.Result replay = WidgetTimerEngine.apply(before, command("stop", 7L, 4500L),
                new WidgetTimerEngine.Category(7L, "副业研发", true), Collections.singleton("cmd-1"));
        assertEquals("noop", replay.status); assertSame(before, replay.snapshot); assertTrue(replay.sessions.isEmpty());
    }

    @Test public void switchAndStopUseIntegerSecondBoundary() {
        WidgetTimerEngine.Result switched = WidgetTimerEngine.apply(running(), command("switch", 8L, 4500L), new WidgetTimerEngine.Category(8L, "吃饭", true));
        assertEquals(1, switched.sessions.size());
        assertEquals(3L, switched.sessions.get(0).durationSeconds);
        assertEquals(Long.valueOf(8L), switched.snapshot.categoryId);
        assertEquals(Long.valueOf(4500L), switched.snapshot.startedAtEpochMs);
        WidgetTimerEngine.Result stopped = WidgetTimerEngine.apply(running(), command("stop", 7L, 4750L), new WidgetTimerEngine.Category(7L, "副业研发", true));
        assertEquals("stopped", stopped.snapshot.state);
        assertEquals(3L, stopped.sessions.get(0).durationSeconds);
    }

    @Test public void pausedStopUsesFrozenNetTimeAndWritesCompatibleSnapshot() {
        WidgetTimerEngine.Snapshot paused = new WidgetTimerEngine.Snapshot(
                "countup_studying", true, 7L, "副业研发", 5000L, 2300L, 1000L);
        WidgetTimerEngine.Result result = WidgetTimerEngine.apply(paused, command("stop", 7L, 9000L),
                new WidgetTimerEngine.Category(7L, "副业研发", true));
        assertEquals(2L, result.sessions.get(0).durationSeconds);
        Map<String, Object> compatible = result.snapshot.toCompatibleMap();
        assertEquals(1, compatible.get("version"));
        assertEquals("stopped", compatible.get("state"));
        assertFalse(compatible.containsKey("transition"));
        assertEquals(null, ((Map<?, ?>) compatible.get("session")).get("startedAtEpochMs"));
        assertEquals("countdown", ((Map<?, ?>) compatible.get("timing")).get("mode"));
    }
}
