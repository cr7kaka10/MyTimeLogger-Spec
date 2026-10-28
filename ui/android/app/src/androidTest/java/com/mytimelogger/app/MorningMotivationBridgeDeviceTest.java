package com.mytimelogger.app;

import static org.junit.Assert.*;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import java.time.LocalDate;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import android.Manifest;
import androidx.test.platform.app.InstrumentationRegistry;

@RunWith(AndroidJUnit4.class)
public class MorningMotivationBridgeDeviceTest {
    @Test public void cachesOnlyValidatedCurrentAccountWeekAndClearsOnLogout() throws Exception {
        try (DietReminderFixture fixture = new DietReminderFixture()) {
            fixture.setup();
            MorningMotivationBridge bridge = new MorningMotivationBridge(fixture.context);
            String today = DailyWidgetStore.dayAt(System.currentTimeMillis());
            JSONArray items = new JSONArray();
            for (int i = 0; i < 7; i++) items.put(new JSONObject()
                .put("date", LocalDate.parse(today).plusDays(i).toString())
                .put("message", "今天先完成第" + i + "件小事，让行动带来新的节奏。"));
            String payload = new JSONObject().put("version", "morning-motivation-v1").put("items", items).toString();
            assertTrue(bridge.cacheWeek(payload));
            assertTrue(MorningMotivationStore.today(fixture.context, today).contains("第0件"));
            items.getJSONObject(1).put("date", "2026-01-01");
            assertFalse(bridge.cacheWeek(new JSONObject().put("version", "morning-motivation-v1").put("items", items).toString()));
            fixture.runtime.edit().remove("runtime").commit();
            assertNull(MorningMotivationStore.today(fixture.context, today));
            bridge.clear();
            assertFalse(fixture.context.getSharedPreferences("morning_motivation_v1", 0).getAll().containsKey("diet-test:" + today));
        }
    }
    @Test public void trialDoesNotConsumeDailyNotificationAndDisableStopsIt() {
        try (DietReminderFixture fixture = new DietReminderFixture()) {
            fixture.setup();
            if (!fixture.hadPermission) InstrumentationRegistry.getInstrumentation().getUiAutomation()
                .grantRuntimePermission(fixture.context.getPackageName(), Manifest.permission.POST_NOTIFICATIONS);
            MorningMotivationBridge bridge = new MorningMotivationBridge(fixture.context);
            assertTrue(bridge.trial());
            assertNull(fixture.motivation.getString("last_notified", null));
            long now = System.currentTimeMillis();
            assertTrue(MorningMotivationNotifier.notifyAt(fixture.context, now, false));
            assertFalse(MorningMotivationNotifier.notifyAt(fixture.context, now, false));
            bridge.setEnabled(false);
            assertFalse(MorningMotivationNotifier.notifyAt(fixture.context, now + 86_400_000, false));
            assertFalse(new JSONObject(bridge.status()).optBoolean("enabled", true));
        } catch (Exception error) { throw new AssertionError(error); }
    }
}
