package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.Calendar;
import org.junit.Test;

public class MealDeadlineScheduleTest {
    @Test public void threeBeijingMealCutoffsAndStaleAlarm() {
        Calendar c = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        c.clear(); c.set(2026, 9, 28, 8, 29);
        assertEquals(3, MealDeadlineSchedule.RULES.length);
        for (int i = 0; i < 3; i++) {
            long at = MealDeadlineSchedule.next(c.getTimeInMillis(), i);
            assertTrue(MealDeadlineSchedule.isDue(at, i));
            assertFalse(MealDeadlineSchedule.isDue(at + 120_000, i));
        }
        assertEquals("lunch_on_time", MealDeadlineSchedule.RULES[1]);
    }
}
