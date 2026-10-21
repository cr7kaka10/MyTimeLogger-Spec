package com.mytimelogger.app;

import static org.junit.Assert.*;
import com.google.gson.JsonObject;
import java.time.Instant;
import java.util.Collections;
import java.util.HashMap;
import java.util.Arrays;
import java.util.List;
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

    @Test public void tasksPrecedeHabitsAndHandledHabitsDisappear() {
        DailyWidgetRepository.Row today = new DailyWidgetRepository.Row("task", "t1", "今天", "今天", "2026-10-20", false, false);
        DailyWidgetRepository.Row overdue = new DailyWidgetRepository.Row("task", "t2", "过期", "10-19", "2026-10-20", false, false);
        DailyWidgetRepository.Row habit = new DailyWidgetRepository.Row("habit", "h1", "习惯", "习惯", "2026-10-20", false, false);
        List<DailyWidgetRepository.Row> rows = DailyWidgetRepository.assemble(
                Collections.singletonList(today), Collections.singletonList(overdue), Collections.singletonList(habit));
        assertEquals(Arrays.asList("今日任务", "今天", "已过期", "过期", "今日习惯", "习惯"),
                Arrays.asList(rows.get(0).title, rows.get(1).title, rows.get(2).title,
                        rows.get(3).title, rows.get(4).title, rows.get(5).title));
        assertEquals(0, DailyWidgetRepository.assemble(Collections.emptyList(), Collections.emptyList(), Collections.emptyList()).size());
        assertTrue(DailyWidgetRepository.unhandled(0));
        assertFalse(DailyWidgetRepository.unhandled(1));
        assertFalse(DailyWidgetRepository.unhandled(2));
        assertEquals("处理中", DailyWidgetRepository.badge("习惯", "pending"));
        assertEquals("重试", DailyWidgetRepository.badge("今天", "failed"));
        assertEquals("今天", DailyWidgetRepository.badge("今天", ""));
    }

    @Test public void actionAndSnapshotMustMatchTodayAndOwner() {
        JsonObject snapshot = new JsonObject(), command = new JsonObject();
        snapshot.addProperty("userId", "7"); snapshot.addProperty("generation", 5);
        snapshot.addProperty("database", "account-7.db");
        command.addProperty("userId", "7"); command.addProperty("generation", 5);
        command.addProperty("database", "account-7.db"); command.addProperty("date", "2026-10-20");
        command.addProperty("kind", "habit"); command.addProperty("id", "h1"); command.addProperty("action", "fail");
        assertTrue(DailyWidgetHeadlessExecutor.valid(snapshot, command, "2026-10-20"));
        command.addProperty("kind", "task");
        assertFalse(DailyWidgetHeadlessExecutor.valid(snapshot, command, "2026-10-20"));
        command.addProperty("action", "complete");
        assertFalse(DailyWidgetHeadlessExecutor.valid(snapshot, command, "2026-10-21"));
        command.addProperty("date", "2026-10-21"); command.addProperty("userId", "8");
        assertFalse(DailyWidgetHeadlessExecutor.valid(snapshot, command, "2026-10-21"));
    }
}
