package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class DietCheckinReminderTest {
    @Test public void schedulesAtBeijing2250AcrossDays() {
        Calendar c = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        c.clear(); c.set(2026, 9, 28, 22, 49);
        long before = c.getTimeInMillis();
        c.set(Calendar.MINUTE, 50);
        assertEquals(c.getTimeInMillis(), DietCheckinReminderSchedule.next(before));
        c.add(Calendar.DAY_OF_MONTH, 1);
        assertEquals(c.getTimeInMillis(), DietCheckinReminderSchedule.next(before + 60_000));
        assertTrue(DietCheckinReminderSchedule.trainingDay(before));
        c.set(2026, 9, 31, 22, 49);
        assertFalse(DietCheckinReminderSchedule.trainingDay(c.getTimeInMillis()));
    }
    @Test public void onlyPendingQualityConstraintsNeedReminder() {
        assertTrue(DietCheckinReminderStore.shouldRemind(Collections.emptyList()));
        List<Map<String, Object>> rows = new ArrayList<>();
        rows.add(Collections.singletonMap("status", "completed"));
        rows.add(Collections.singletonMap("status", "failed"));
        assertTrue(DietCheckinReminderStore.shouldRemind(rows));
        rows.add(Collections.singletonMap("status", "completed"));
        assertFalse(DietCheckinReminderStore.shouldRemind(rows));
    }
}
