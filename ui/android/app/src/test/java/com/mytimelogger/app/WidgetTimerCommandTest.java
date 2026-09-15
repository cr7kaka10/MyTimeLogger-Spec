package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.Test;

public class WidgetTimerCommandTest {
    private static Map<String, Object> valid(String action) {
        Map<String, Object> value = new HashMap<>();
        value.put("action", action); value.put("commandId", "widget-1");
        value.put("categoryId", 7L); value.put("eventEpochMs", 1721337600000L);
        return value;
    }

    @Test public void sharedV1FixtureMatchesJavaWhitelist() throws Exception {
        String fixture = new String(Files.readAllBytes(Paths.get("..", "..", "..", "shared", "protocol", "timer-widget-command.v1.json")), StandardCharsets.UTF_8);
        for (String token : Arrays.asList("start", "switch", "stop", "commandId", "categoryId", "eventEpochMs"))
            assertTrue(token, fixture.contains("\"" + token + "\""));
        for (String action : Arrays.asList("start", "switch", "stop"))
            assertEquals(action, WidgetTimerCommand.parse(valid(action)).action);
    }

    @Test public void invalidFieldsTimesAndStructuredNamesAreRejected() {
        assertThrows(IllegalArgumentException.class, () -> WidgetTimerCommand.parse(valid("pause")));
        Map<String, Object> extra = valid("start"); extra.put("note", "secret");
        assertThrows(IllegalArgumentException.class, () -> WidgetTimerCommand.parse(extra));
        Map<String, Object> badTime = valid("start"); badTime.put("eventEpochMs", 0L);
        assertThrows(IllegalArgumentException.class, () -> WidgetTimerCommand.parse(badTime));
        assertTrue(WidgetTimerCommand.isBlockedCategoryName("输入"));
        assertTrue(WidgetTimerCommand.isBlockedCategoryName("输出"));
        assertFalse(WidgetTimerCommand.isBlockedCategoryName("副业研发"));
    }
}
