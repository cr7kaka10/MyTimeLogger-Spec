package com.mytimelogger.app;

import android.Manifest;
import android.app.NotificationManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.gson.JsonObject;
import java.util.Collections;

final class DietReminderFixture implements AutoCloseable {
    final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    final String name = "diet-reminder-device-test.db";
    final SharedPreferences storage = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE);
    final SharedPreferences runtime = context.getSharedPreferences("mtl_widget_runtime_v1", Context.MODE_PRIVATE);
    final SharedPreferences sent = context.getSharedPreferences("diet_reminder_v1", Context.MODE_PRIVATE);
    final SharedPreferences mealSent = context.getSharedPreferences("meal_deadline_v1", Context.MODE_PRIVATE);
    final SharedPreferences motivation = context.getSharedPreferences("morning_motivation_v1", Context.MODE_PRIVATE);
    final String oldDb = storage.getString(WidgetTimerPreferences.ACTIVE_DB_KEY, null);
    final String oldRuntime = runtime.getString("runtime", null);
    final String oldSent = sent.getString("last_notified", null);
    final String oldMealSent = mealSent.getString("last_1", null);
    final String oldMotivationLast = motivation.getString("last_notified", null);
    final boolean oldMotivationEnabled = motivation.getBoolean("enabled", true);
    final boolean hadPermission = context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
    final SqliteConnection db = new SqliteConnection(context, name);

    void setup() {
        context.deleteDatabase(name); db.open();
        db.execute("CREATE TABLE system_config(key TEXT,value TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE exercise_diet_checkins(date TEXT,plan_version TEXT,rule_key TEXT,status TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE exercise_plan_items(id TEXT,plan_version TEXT,day_key TEXT,variant TEXT,is_active INTEGER)", Collections.emptyList());
        db.execute("INSERT INTO exercise_plan_items VALUES('wednesday','v5','周三','gym',1)", Collections.emptyList());
        db.execute("INSERT INTO system_config VALUES('active_exercise_plan_version','v5')", Collections.emptyList());
        for (String key : new String[]{"no_sugary_drinks","no_refined_staples","no_snacks"})
            db.execute("INSERT INTO exercise_diet_checkins VALUES('2026-10-28','v5',?,'pending')", Collections.singletonList(key));
        for (String key : MealDeadlineSchedule.RULES)
            db.execute("INSERT INTO exercise_diet_checkins VALUES('2026-10-28','v5',?,'pending')", Collections.singletonList(key));
        JsonObject config = new JsonObject();
        config.addProperty("serverUrl", "http://127.0.0.1:9"); config.addProperty("authToken", "isolated-test");
        config.addProperty("deviceId", "diet-test"); config.addProperty("verifiedUserId", "diet-test"); config.addProperty("generation", 888);
        if (!new WidgetTimerRuntimeStore(context).configure(config.toString())) throw new AssertionError("runtime setup failed");
        storage.edit().putString(WidgetTimerPreferences.ACTIVE_DB_KEY, name).commit();
        sent.edit().remove("last_notified").commit();
        mealSent.edit().remove("last_1").commit();
        motivation.edit().remove("last_notified").putBoolean("enabled", true).commit();
    }
    @Override public void close() {
        db.close(); context.deleteDatabase(name);
        restore(storage, WidgetTimerPreferences.ACTIVE_DB_KEY, oldDb);
        restore(runtime, "runtime", oldRuntime); restore(sent, "last_notified", oldSent);
        restore(mealSent, "last_1", oldMealSent);
        restore(motivation, "last_notified", oldMotivationLast);
        motivation.edit().putBoolean("enabled", oldMotivationEnabled).commit();
        MorningMotivationStore.clear(context, "diet-test");
        context.getSystemService(NotificationManager.class).cancel(852);
        context.getSystemService(NotificationManager.class).cancel(861);
        context.getSystemService(NotificationManager.class).cancel(870);
        context.getSystemService(NotificationManager.class).cancel(871);
        if (!hadPermission) InstrumentationRegistry.getInstrumentation().getUiAutomation().revokeRuntimePermission(context.getPackageName(), Manifest.permission.POST_NOTIFICATIONS);
    }
    private static void restore(SharedPreferences prefs, String key, String value) {
        SharedPreferences.Editor edit = prefs.edit();
        if (value == null) edit.remove(key); else edit.putString(key, value);
        edit.commit();
    }
}
