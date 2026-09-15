package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class TimerWidgetBootReceiverTest {
    @Test public void bootRecoversEpochElapsedAndNeverClearsStructuredSnapshot() {
        List<String> reasons = new ArrayList<>();
        TimerWidgetRenderer.setRefreshSinkForTest((context, reason) -> reasons.add(reason));
        WidgetTimerEngine.Snapshot running = new WidgetTimerEngine.Snapshot(
                "countup_studying", false, 7L, "运动", 1000L, 2500L, 500L);
        assertEquals(6500L, TimerWidgetBootReceiver.recoveredElapsed(running, 5000L));
        WidgetTimerEngine.Snapshot paused = new WidgetTimerEngine.Snapshot(
                "countup_studying", true, 7L, "运动", 1000L, 2500L, 500L);
        assertEquals(2500L, TimerWidgetBootReceiver.recoveredElapsed(paused, 5000L));
        WidgetTimerEngine.Snapshot structured = new WidgetTimerEngine.Snapshot(
                "studying", false, 1L, "输入", 1000L, 0L, 500L);
        assertSame(structured, TimerWidgetBootReceiver.preserve(structured));
        TimerWidgetBootReceiver.refreshForTest();
        assertEquals(Collections.singletonList("boot"), reasons);
        TimerWidgetRenderer.setRefreshSinkForTest(null);
    }
}
