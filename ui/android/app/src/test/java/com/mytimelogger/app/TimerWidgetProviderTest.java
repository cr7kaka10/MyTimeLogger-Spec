package com.mytimelogger.app;

import static org.junit.Assert.assertEquals;
import java.util.*;
import org.junit.Test;

public class TimerWidgetProviderTest {
    @Test public void allLifecyclePathsShareRefreshWithoutDeletingState() {
        List<String> reasons = new ArrayList<>();
        TimerWidgetRenderer.setRefreshSinkForTest((context, reason) -> reasons.add(reason));
        TimerWidgetProvider.refreshForTest("enable");
        TimerWidgetProvider.refreshForTest("update");
        TimerWidgetProvider.refreshForTest("update");
        TimerWidgetProvider.refreshForTest("options");
        TimerWidgetProvider.refreshForTest("theme");
        TimerWidgetProvider.refreshForTest("command");
        TimerWidgetProvider.deleteForTest();
        assertEquals(Arrays.asList("enable", "update", "update", "options", "theme", "command"), reasons);
        TimerWidgetRenderer.setRefreshSinkForTest(null);
    }

    @Test public void appStopRefreshWinsOverLateRunningRevision() {
        List<String> reasons = new ArrayList<>();
        TimerWidgetRenderer.setRefreshSinkForTest((context, reason) -> reasons.add(reason));
        TimerWidgetProvider.resetRevisionForTest();
        assertEquals(true, TimerWidgetProvider.refreshRevisionForTest("app-stopped", 12L));
        assertEquals(false, TimerWidgetProvider.refreshRevisionForTest("late-running", 11L));
        assertEquals(true, TimerWidgetProvider.refreshRevisionForTest("same-stopped", 12L));
        assertEquals(Arrays.asList("app-stopped", "same-stopped"), reasons);
        TimerWidgetRenderer.setRefreshSinkForTest(null);
    }
}
