package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class WidgetTimerBridgeTest {
    private static WidgetTimerCommand command(String id) {
        Map<String, Object> value = new HashMap<>();
        value.put("action", "start"); value.put("commandId", id);
        value.put("categoryId", 7L); value.put("eventEpochMs", 123L);
        return WidgetTimerCommand.parse(value);
    }

    @Test public void dispatchesOnlyReadyOrdinaryCommandsAndTracksAck() {
        List<String> scripts = new ArrayList<>();
        int[] refreshes = { 0 };
        WidgetTimerBridge bridge = new WidgetTimerBridge(scripts::add, () -> refreshes[0]++);
        WidgetTimerBridge.attach(bridge);
        bridge.refresh();
        assertEquals(1, refreshes[0]);
        assertFalse(bridge.dispatch(command("cmd-1"), "运动"));
        bridge.ready();
        assertTrue(bridge.dispatch(command("cmd-1"), "运动"));
        assertTrue(scripts.get(0).contains("cmd-1"));
        bridge.authoritativeStateChanged();
        assertTrue(scripts.get(1).contains("mtl:timer-widget-snapshot-changed"));
        assertFalse(scripts.get(1).contains("detail:"));
        assertFalse(bridge.dispatch(command("cmd-2"), "输入"));
        bridge.ack("cmd-1", "applied");
        bridge.ack("bad id", "applied");
        assertEquals("applied", bridge.ackResult("cmd-1"));
        assertNull(bridge.ackResult("bad id"));
        bridge.close();
        assertNull(WidgetTimerBridge.current());
        assertFalse(bridge.dispatch(command("cmd-3"), "运动"));
        bridge.refresh();
        assertEquals(1, refreshes[0]);
    }
}
