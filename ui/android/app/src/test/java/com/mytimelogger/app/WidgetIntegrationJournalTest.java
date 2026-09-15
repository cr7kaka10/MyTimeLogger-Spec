package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class WidgetIntegrationJournalTest {
    private static final class MemoryBackend implements WidgetTimerPreferences.Backend {
        final Map<String, String> values = new HashMap<>();
        public String get(String key) { return values.get(key); }
        public void put(String key, String value) { values.put(key, value); }
    }
    private static WidgetTimerCommand command(String id, String action, long categoryId, long at) {
        Map<String, Object> value = new HashMap<>();
        value.put("commandId", id); value.put("action", action);
        value.put("categoryId", categoryId); value.put("eventEpochMs", at);
        return WidgetTimerCommand.parse(value);
    }

    @Test public void journalDeduplicatesPersistsAndKeepsBoundedEvents() {
        MemoryBackend backend = new MemoryBackend();
        WidgetIntegrationJournal journal = new WidgetIntegrationJournal(backend, 2);
        assertTrue(journal.append(command("one", "start", 7L, 1000L)));
        assertFalse(journal.append(command("one", "start", 7L, 1000L)));
        assertTrue(journal.append(command("two", "switch", 8L, 2000L)));
        assertTrue(journal.append(command("three", "stop", 8L, 3000L)));
        WidgetIntegrationJournal restored = new WidgetIntegrationJournal(backend, 2);
        assertEquals(2, restored.events().size());
        assertEquals("two", restored.events().get(0).commandId);
        assertEquals("three", restored.events().get(1).commandId);
    }

    @Test public void persistedPayloadContainsOnlyDeidentifiedWhitelist() {
        MemoryBackend backend = new MemoryBackend();
        WidgetIntegrationJournal journal = new WidgetIntegrationJournal(backend, 4);
        journal.append(command("safe-1", "start", 7L, 1000L));
        String raw = journal.rawJson();
        for (String forbidden : Arrays.asList("account", "password", "token", "Authorization", "activityId", "response", "note"))
            assertFalse(forbidden, raw.contains(forbidden));
        assertEquals("[{\"commandId\":\"safe-1\",\"action\":\"start\",\"categoryId\":7,\"eventEpochMs\":1000}]", raw);
    }
}
