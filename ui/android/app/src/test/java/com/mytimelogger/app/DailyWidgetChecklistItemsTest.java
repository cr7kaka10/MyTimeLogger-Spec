package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.List;
import org.junit.Test;

public class DailyWidgetChecklistItemsTest {
    @Test public void sortsStablyAndCountsOnlyCompletedItems() {
        List<DailyWidgetChecklistItems.Entry> items = DailyWidgetChecklistItems.parse(
                "{\"items\":[{\"id\":\"last\",\"title\":\"尾\",\"status\":2,\"sortOrder\":8},"
                + "{\"id\":\"first\",\"title\":\"首\",\"status\":0,\"sortOrder\":1},"
                + "{\"id\":\"same\",\"title\":\"同\",\"status\":0,\"sortOrder\":8}]}"
        );
        assertEquals(3, items.size());
        assertEquals("first", items.get(0).id);
        assertEquals("last", items.get(1).id);
        assertEquals("same", items.get(2).id);
        assertFalse(items.get(0).done());
        assertTrue(items.get(1).done());
    }

    @Test public void absentEmptyAndMalformedItemsDoNotBreakOtherTasks() {
        assertTrue(DailyWidgetChecklistItems.parse(null).isEmpty());
        assertTrue(DailyWidgetChecklistItems.parse("not-json").isEmpty());
        assertTrue(DailyWidgetChecklistItems.parse("{}").isEmpty());
        assertTrue(DailyWidgetChecklistItems.parse("{\"items\":[]}").isEmpty());
        assertEquals(1, DailyWidgetChecklistItems.parse(
                "{\"items\":[null,{\"id\":\"\",\"title\":\"x\",\"status\":0},"
                + "{\"id\":\"ok\",\"title\":\"安全\",\"status\":0}]}").size());
    }
}
