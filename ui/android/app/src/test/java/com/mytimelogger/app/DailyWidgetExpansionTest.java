package com.mytimelogger.app;

import static org.junit.Assert.*;
import com.google.gson.JsonObject;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.junit.Test;

public class DailyWidgetExpansionTest {
    @Test public void expandedStateBelongsToCurrentAccountGenerationAndBeijingDay() {
        String day = DailyWidgetStore.today();
        JsonObject owner = new JsonObject(), state = new JsonObject();
        owner.addProperty("userId", "7"); owner.addProperty("database", "account.db");
        owner.addProperty("generation", 3);
        state.addProperty("userId", "7"); state.addProperty("database", "account.db");
        state.addProperty("generation", 3); state.addProperty("date", day);
        state.addProperty("id", "task-1");
        assertTrue(DailyWidgetStore.expandedMatches(owner, state, "task-1", day));
        assertFalse(DailyWidgetStore.expandedMatches(owner, state, "task-2", day));
        assertFalse(DailyWidgetStore.expandedMatches(owner, state, "task-1", "2020-01-01"));
        owner.addProperty("generation", 4);
        assertFalse(DailyWidgetStore.expandedMatches(owner, state, "task-1", day));
        owner.addProperty("generation", 3); owner.addProperty("userId", "8");
        assertFalse(DailyWidgetStore.expandedMatches(owner, state, "task-1", day));
    }

    @Test public void childRowsDoNotIncreaseParentTaskCount() {
        DailyWidgetRepository.Row parent = new DailyWidgetRepository.Row("task", "task-1", "任务", "今天",
                "2026-10-27", false, false, "task-1", "1/2", true);
        DailyWidgetRepository.Row child = new DailyWidgetRepository.Row("checklist_item", "item-1", "步骤", "",
                "2026-10-27", false, false, "task-1", "", false);
        List<DailyWidgetRepository.Row> rows = DailyWidgetRepository.assemble(
                Arrays.asList(parent, child), Collections.emptyList(), Collections.emptyList());
        assertEquals("1", rows.get(0).badge);
        assertEquals("task", rows.get(1).kind);
        assertEquals("checklist_item", rows.get(2).kind);
        assertEquals("task-1", rows.get(2).parentId);
    }
}
