package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.Calendar;
import org.junit.Test;

public class MorningMotivationScheduleTest {
    @Test public void nextMorningAtBeijing0730WithoutOldBackfill() {
        Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        day.clear(); day.set(2026, 9, 29, 7, 29);
        long before = day.getTimeInMillis(); day.set(Calendar.MINUTE, 30);
        long at = day.getTimeInMillis();
        assertEquals(at, MorningMotivationReceiver.next(before));
        assertTrue(MorningMotivationReceiver.due(at));
        assertFalse(MorningMotivationReceiver.due(at + 120_000));
        day.add(Calendar.DAY_OF_MONTH, 1);
        assertEquals(day.getTimeInMillis(), MorningMotivationReceiver.next(at));
    }
}
