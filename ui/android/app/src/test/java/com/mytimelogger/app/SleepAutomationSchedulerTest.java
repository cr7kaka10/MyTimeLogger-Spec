package com.mytimelogger.app;

import static org.junit.Assert.assertEquals;
import java.util.Calendar;
import java.util.TimeZone;
import org.junit.Test;

public class SleepAutomationSchedulerTest {
    private static long at(TimeZone zone, int day, int hour, int minute) {
        Calendar c = Calendar.getInstance(zone); c.clear();
        c.set(2026, Calendar.SEPTEMBER, day, hour, minute, 0);
        return c.getTimeInMillis();
    }

    @Test public void schedulesSameDayAt0839() {
        assertEquals(at(SleepAutomationScheduler.BEIJING, 29, 8, 40),
                SleepAutomationScheduler.next840(at(SleepAutomationScheduler.BEIJING, 29, 8, 39)));
    }

    @Test public void exact0840AndLateTimeScheduleNextDay() {
        assertEquals(at(SleepAutomationScheduler.BEIJING, 30, 8, 40),
                SleepAutomationScheduler.next840(at(SleepAutomationScheduler.BEIJING, 29, 8, 40)));
        assertEquals(at(SleepAutomationScheduler.BEIJING, 30, 8, 40),
                SleepAutomationScheduler.next840(at(SleepAutomationScheduler.BEIJING, 29, 23, 59)));
    }

    @Test public void ignoresDeviceTimeZoneAndHasTwentyMinuteWindow() {
        long start = SleepAutomationScheduler.next840(at(TimeZone.getTimeZone("America/New_York"), 28, 20, 39));
        assertEquals(at(SleepAutomationScheduler.BEIJING, 29, 8, 40), start);
        assertEquals(20L * 60L * 1000L, SleepAutomationScheduler.windowEnd(start) - start);
    }
}
