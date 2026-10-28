package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.Manifest;
import android.app.NotificationManager;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.Calendar;
import java.util.Collections;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class MealDeadlineDeviceTest {
    @Test public void completedMealIsSilentAndPendingMealPromptsOnce() {
        try (DietReminderFixture fixture = new DietReminderFixture()) {
            fixture.setup();
            Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
            day.clear(); day.set(2026, 9, 28, 13, 31); long at = day.getTimeInMillis();
            assertTrue(MealDeadlineState.pending(fixture.context, at, 1));
            fixture.db.execute("UPDATE exercise_diet_checkins SET status='completed' WHERE rule_key='lunch_on_time'", Collections.emptyList());
            assertFalse(MealDeadlineState.pending(fixture.context, at, 1));
            MealDeadlineReceiver.deliverAt(fixture.context, at, 1);
            assertFalse(java.util.Arrays.stream(fixture.context.getSystemService(NotificationManager.class)
                .getActiveNotifications()).anyMatch(item -> item.getId() == 861));
            fixture.db.execute("UPDATE exercise_diet_checkins SET status='pending' WHERE rule_key='lunch_on_time'", Collections.emptyList());
            if (!fixture.hadPermission) InstrumentationRegistry.getInstrumentation().getUiAutomation()
                .grantRuntimePermission(fixture.context.getPackageName(), Manifest.permission.POST_NOTIFICATIONS);
            MealDeadlineReceiver.deliverAt(fixture.context, at, 1);
            MealDeadlineReceiver.deliverAt(fixture.context, at, 1);
            assertTrue(java.util.Arrays.stream(fixture.context.getSystemService(NotificationManager.class)
                .getActiveNotifications()).anyMatch(item -> item.getId() == 861));
            day.add(Calendar.DAY_OF_MONTH, 3);
            assertFalse(MealDeadlineState.pending(fixture.context, day.getTimeInMillis(), 1));
            fixture.runtime.edit().remove("runtime").commit();
            assertFalse(MealDeadlineState.pending(fixture.context, at, 1));
        }
    }
}
