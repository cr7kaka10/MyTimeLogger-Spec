package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.Calendar;
import java.util.TimeZone;
import org.junit.Test;

public class SleepAutomationSchedulerTest {
    private static long at(TimeZone zone, int day, int hour, int minute) {
        Calendar c = Calendar.getInstance(zone); c.clear();
        c.set(2026, Calendar.SEPTEMBER, day, hour, minute, 0);
        return c.getTimeInMillis();
    }

    @Test public void schedulesSameDayAt0835() {
        assertEquals(at(SleepAutomationScheduler.BEIJING, 29, 8, 35),
                SleepAutomationScheduler.nextWindowStart(at(SleepAutomationScheduler.BEIJING, 29, 8, 34)));
    }

    @Test public void exact0835AndLateTimeScheduleNextDay() {
        assertEquals(at(SleepAutomationScheduler.BEIJING, 30, 8, 35),
                SleepAutomationScheduler.nextWindowStart(at(SleepAutomationScheduler.BEIJING, 29, 8, 35)));
        assertEquals(at(SleepAutomationScheduler.BEIJING, 30, 8, 35),
                SleepAutomationScheduler.nextWindowStart(at(SleepAutomationScheduler.BEIJING, 29, 23, 59)));
    }

    @Test public void ignoresDeviceTimeZoneAndHasTwentyMinuteWindow() {
        long start = SleepAutomationScheduler.nextWindowStart(at(TimeZone.getTimeZone("America/New_York"), 28, 20, 34));
        assertEquals(at(SleepAutomationScheduler.BEIJING, 29, 8, 35), start);
        assertEquals(5L * 60L * 1000L, SleepAutomationScheduler.windowEnd(start) - start);
        assertTrue(SleepAutomationScheduler.withinUnlockWindow(start, start));
        assertTrue(SleepAutomationScheduler.withinUnlockWindow(start + 5L * 60L * 1000L, start));
        assertFalse(SleepAutomationScheduler.withinUnlockWindow(start + 5L * 60L * 1000L + 1, start));
    }
}
