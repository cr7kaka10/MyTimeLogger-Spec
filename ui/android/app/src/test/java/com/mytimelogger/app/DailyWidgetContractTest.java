package com.mytimelogger.app;

import static org.junit.Assert.*;
import com.google.gson.JsonObject;
import java.time.Instant;
import java.util.Collections;
import java.util.HashMap;
import org.junit.Test;

public class DailyWidgetContractTest {
    @Test public void beijingMidnightAndDueBucketsStayStable() {
        long before = Instant.parse("2026-10-19T15:59:59Z").toEpochMilli();
        long after = Instant.parse("2026-10-19T16:00:00Z").toEpochMilli();
        assertEquals("2026-10-19", DailyWidgetStore.dayAt(before));
        assertEquals("2026-10-20", DailyWidgetStore.dayAt(after));
        assertEquals(-1, DailyWidgetRepository.dueBucket("2026-10-19 23:59:59", "2026-10-20"));
        assertEquals(0, DailyWidgetRepository.dueBucket("2026-10-20 00:00:00", "2026-10-20"));
        assertEquals(1, DailyWidgetRepository.dueBucket("2026-10-21", "2026-10-20"));
        HashMap<String, Integer> checked = new HashMap<>(); checked.put("once", 2);
        assertTrue(DailyWidgetRepository.includeHabit(Collections.emptySet(), checked, "once"));
        assertFalse(DailyWidgetRepository.includeHabit(Collections.emptySet(), checked, "absent"));
    }

    @Test public void snapshotRejectsOldAccountGenerationAndDay() {
        JsonObject value = new JsonObject();
        value.addProperty("userId", "7"); value.addProperty("generation", 42L);
        value.addProperty("database", "account-7.db");
        JsonObject days = new JsonObject(); days.add("2026-10-20", new com.google.gson.JsonArray());
        value.add("days", days);
        assertTrue(DailyWidgetStore.matches(value, "7", 42L, "account-7.db", "2026-10-20"));
        assertFalse(DailyWidgetStore.matches(value, "8", 42L, "account-7.db", "2026-10-20"));
        assertFalse(DailyWidgetStore.matches(value, "7", 43L, "account-7.db", "2026-10-20"));
        assertFalse(DailyWidgetStore.matches(value, "7", 42L, "account-8.db", "2026-10-20"));
        assertFalse(DailyWidgetStore.matches(value, "7", 42L, "account-7.db", "2026-10-21"));
    }

    @Test public void duplicateTapReusesPendingCommandAndConfirmedTapStops() {
        JsonObject pending = new JsonObject(), done = new JsonObject();
        JsonObject command = new JsonObject(); command.addProperty("commandId", "daily-abc");
        String key = "habit:daily-walk:2026-10-20";
        pending.add(key, command);
        assertSame(command, DailyWidgetStore.existingClaim(pending, done, key));
        assertSame(command, DailyWidgetStore.existingClaim(pending, done, key));
        done.addProperty(key, "applied");
        assertNull(DailyWidgetStore.existingClaim(pending, done, key));
    }

    @Test public void sameAccountRestartKeepsTodayCommandIdentity() {
        JsonObject pending = new JsonObject();
        JsonObject today = new JsonObject();
        today.addProperty("date", "2026-10-20"); today.addProperty("generation", 1);
        today.addProperty("commandId", "daily-fixed");
        JsonObject yesterday = new JsonObject(); yesterday.addProperty("date", "2026-10-19");
        pending.add("task:a:2026-10-20", today); pending.add("task:b:2026-10-19", yesterday);
        JsonObject restored = DailyWidgetStore.rebasePending(pending, "2026-10-20", 2);
        assertEquals(1, restored.size());
        assertEquals(2, restored.getAsJsonObject("task:a:2026-10-20").get("generation").getAsInt());
        assertEquals("daily-fixed", restored.getAsJsonObject("task:a:2026-10-20").get("commandId").getAsString());
    }
}
