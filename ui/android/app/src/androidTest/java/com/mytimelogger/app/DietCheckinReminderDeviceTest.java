package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.Manifest;
import android.app.NotificationManager;
import android.content.Intent;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collections;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class DietCheckinReminderDeviceTest {
    @Test public void checksIsolatedAccountAndDeliversOnce() {
        try (DietReminderFixture fixture = new DietReminderFixture()) {
            fixture.setup();
            Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
            day.clear(); day.set(2026, 9, 28, 22, 50); long at = day.getTimeInMillis();
            assertTrue(DietCheckinReminderStore.needsReminder(fixture.context, at));
            if (!fixture.hadPermission) {
                DietCheckinReminderReceiver.deliverAt(fixture.context, at);
                assertEquals("", fixture.sent.getString("last_notified", ""));
                InstrumentationRegistry.getInstrumentation().getUiAutomation().grantRuntimePermission(
                    fixture.context.getPackageName(), Manifest.permission.POST_NOTIFICATIONS);
            }
            DietCheckinReminderReceiver.deliverAt(fixture.context, at);
            assertEquals(fixture.name + ":2026-10-28", fixture.sent.getString("last_notified", ""));
            assertTrue(Arrays.stream(fixture.context.getSystemService(NotificationManager.class)
                .getActiveNotifications()).anyMatch(notification -> notification.getId() == 852));
            DietCheckinReminderReceiver.deliverAt(fixture.context, at);
            assertEquals(fixture.name + ":2026-10-28", fixture.sent.getString("last_notified", ""));
            fixture.db.execute("UPDATE exercise_diet_checkins SET status='completed'", Collections.emptyList());
            assertFalse(DietCheckinReminderStore.needsReminder(fixture.context, at));
            day.add(Calendar.DAY_OF_MONTH, 3);
            assertFalse(DietCheckinReminderStore.needsReminder(fixture.context, day.getTimeInMillis()));
            fixture.runtime.edit().remove("runtime").commit();
            assertFalse(DietCheckinReminderStore.needsReminder(fixture.context, at));
            new DietCheckinReminderReceiver().onReceive(fixture.context, new Intent(Intent.ACTION_BOOT_COMPLETED));
        }
    }
}
