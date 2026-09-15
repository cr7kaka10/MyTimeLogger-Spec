package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class WidgetTimerPreferencesTest {
    private static final class MemoryBackend implements WidgetTimerPreferences.Backend {
        final Map<String, String> values = new HashMap<>();
        public String get(String key) { return values.get(key); }
        public void put(String key, String value) { values.put(key, value); }
    }
    private static final String VALID = "{\"version\":1,\"capturedAtEpochMs\":1000,\"state\":\"stopped\",\"isPaused\":false,"
            + "\"category\":{},\"pause\":{},\"segments\":[],\"session\":{},\"timing\":{}}";

    @Test public void snapshotUsesCapacitorKeyAndRejectsCorruptionWithoutOverwrite() {
        MemoryBackend backend = new MemoryBackend();
        WidgetTimerPreferences preferences = new WidgetTimerPreferences(backend);
        assertTrue(preferences.saveSnapshot(VALID));
        assertEquals(VALID, backend.values.get("mtl.runtime.timer.logic.snapshot.v1"));
        assertFalse(preferences.saveSnapshot("{broken"));
        assertFalse(preferences.saveSnapshot(VALID.replace("\"version\":1", "\"version\":2")));
        assertEquals(VALID, preferences.loadSnapshot());
    }

    @Test public void commandStateRoundTripsOnlyJsonObjects() {
        MemoryBackend backend = new MemoryBackend();
        WidgetTimerPreferences preferences = new WidgetTimerPreferences(backend);
        assertTrue(preferences.saveCommandState("{\"cmd-1\":\"applied\"}"));
        assertEquals("{\"cmd-1\":\"applied\"}", preferences.loadCommandState());
        assertFalse(preferences.saveCommandState("[]"));
        assertEquals("{\"cmd-1\":\"applied\"}", preferences.loadCommandState());
    }

    @Test public void activeDatabaseNameReturnsWrittenName() {
        MemoryBackend backend = new MemoryBackend();
        backend.put("mtl.runtime.widget.active_database_name", "mtl-acct-0123456789abcdef0123456789abcdef.db");
        WidgetTimerPreferences preferences = new WidgetTimerPreferences(backend);
        assertEquals("mtl-acct-0123456789abcdef0123456789abcdef.db", preferences.loadActiveDatabaseName());
    }

    @Test public void activeDatabaseNameReturnsNullWhenMissingOrInvalid() {
        MemoryBackend backend = new MemoryBackend();
        WidgetTimerPreferences preferences = new WidgetTimerPreferences(backend);
        assertNull(preferences.loadActiveDatabaseName());
        backend.put("mtl.runtime.widget.active_database_name", "");
        assertNull(preferences.loadActiveDatabaseName());
        backend.put("mtl.runtime.widget.active_database_name", "no-extension");
        assertNull(preferences.loadActiveDatabaseName());
        backend.put("mtl.runtime.widget.active_database_name", "mtl-bootstrap.db");
        assertEquals("mtl-bootstrap.db", preferences.loadActiveDatabaseName());
    }
}
