package com.mytimelogger.app;

import android.content.Context;
import java.util.Arrays;
import java.util.Calendar;
import java.util.List;
import java.util.Map;

final class MealDeadlineState {
    static boolean pending(Context context, long now, int meal) {
        if (new WidgetTimerRuntimeStore(context).read() == null) return false;
        String name = new WidgetTimerPreferences(context).loadActiveDatabaseName();
        if (name == null || !context.getDatabasePath(name).isFile()) return false;
        SqliteConnection db = new SqliteConnection(context, name);
        try {
            db.open();
            List<Map<String, Object>> version = db.query("SELECT value FROM system_config WHERE key='active_exercise_plan_version'", Arrays.asList());
            if (version.isEmpty() || !"v5".equals(String.valueOf(version.get(0).get("value")))) return false;
            Calendar calendar = Calendar.getInstance(SleepAutomationScheduler.BEIJING); calendar.setTimeInMillis(now);
            String day = new String[]{"日", "周一", "周二", "周三", "周四", "周五", "六"}[calendar.get(Calendar.DAY_OF_WEEK) - 1];
            List<Map<String, Object>> plan = db.query("SELECT id FROM exercise_plan_items WHERE plan_version='v5' AND day_key=? AND variant IN ('gym','rain') AND is_active=1 LIMIT 1", Arrays.asList(day));
            if (plan.isEmpty()) return false;
            List<Map<String, Object>> rows = db.query("SELECT status FROM exercise_diet_checkins WHERE date=? AND plan_version='v5' AND rule_key=?", Arrays.asList(DailyWidgetStore.dayAt(now), MealDeadlineSchedule.RULES[meal]));
            return shouldRemind(rows);
        } catch (RuntimeException error) {
            android.util.Log.w("MealDeadline", "state_unavailable", error); return false;
        } finally { db.close(); }
    }
    static boolean shouldRemind(List<Map<String, Object>> rows) {
        return rows.size() == 1 && "pending".equals(String.valueOf(rows.get(0).get("status")));
    }
    private MealDeadlineState() {}
}
