package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class SleepAutomationRescheduleReceiverTest {
    @Test public void requiresEnabledAndChangedTarget() {
        assertFalse(SleepAutomationRescheduleReceiver.shouldSchedule(false, 0, 100));
        assertTrue(SleepAutomationRescheduleReceiver.shouldSchedule(true, 100, 100));
        assertTrue(SleepAutomationRescheduleReceiver.shouldSchedule(true, 100, 200));
    }
}
