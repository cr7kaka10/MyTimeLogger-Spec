package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class DailyWidgetTimedHabitTest {
    @Test public void widgetWindowAndTerminalStatusMatchServerBoundaries() {
        int[] window={480,600};
        assertEquals("未到时间",DailyWidgetRepository.windowBlock(window,479));
        assertEquals("",DailyWidgetRepository.windowBlock(window,480));
        assertEquals("",DailyWidgetRepository.windowBlock(window,599));
        assertEquals("已超时",DailyWidgetRepository.windowBlock(window,600));
        assertEquals("",DailyWidgetRepository.windowBlock(null,600));
        assertTrue(DailyWidgetRepository.unhandled(0));
        assertFalse(DailyWidgetRepository.unhandled(1));
        assertFalse(DailyWidgetRepository.unhandled(2));
    }
}
