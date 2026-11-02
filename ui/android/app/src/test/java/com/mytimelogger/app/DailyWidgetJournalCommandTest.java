package com.mytimelogger.app;

import static org.junit.Assert.*;
import com.google.gson.JsonObject;
import org.junit.Test;

public class DailyWidgetJournalCommandTest {
    private static JsonObject snapshot() {
        JsonObject value = new JsonObject();
        value.addProperty("userId", "7"); value.addProperty("generation", 3);
        value.addProperty("database", "account.db");
        return value;
    }

    private static JsonObject command() {
        JsonObject value = new JsonObject();
        value.addProperty("commandId", "daily-habit-1"); value.addProperty("kind", "habit");
        value.addProperty("action", "complete"); value.addProperty("id", "habit-1");
        value.addProperty("date", "2026-11-02"); value.addProperty("userId", "7");
        value.addProperty("generation", 3); value.addProperty("database", "account.db");
        return value;
    }

    @Test public void acceptsOnlyCurrentOwnerDayAndCompleteHabitCommand() {
        JsonObject owner = snapshot(), value = command();
        assertTrue(DailyWidgetHeadlessExecutor.validJournal(owner, value, "daily-habit-1", "2026-11-02"));
        assertFalse(DailyWidgetHeadlessExecutor.validJournal(owner, value, "other", "2026-11-02"));
        assertFalse(DailyWidgetHeadlessExecutor.validJournal(owner, value, "daily-habit-1", "2026-11-03"));
        owner.addProperty("generation", 4);
        assertFalse(DailyWidgetHeadlessExecutor.validJournal(owner, value, "daily-habit-1", "2026-11-02"));
        owner.addProperty("generation", 3); owner.addProperty("userId", "8");
        assertFalse(DailyWidgetHeadlessExecutor.validJournal(owner, value, "daily-habit-1", "2026-11-02"));
        owner.addProperty("userId", "7"); value.addProperty("action", "fail");
        assertFalse(DailyWidgetHeadlessExecutor.validJournal(owner, value, "daily-habit-1", "2026-11-02"));
        value.addProperty("action", "complete"); value.addProperty("kind", "task");
        assertFalse(DailyWidgetHeadlessExecutor.validJournal(owner, value, "daily-habit-1", "2026-11-02"));
        assertFalse(DailyWidgetHeadlessExecutor.validJournal(owner, value, "../bad", "2026-11-02"));
    }
}
