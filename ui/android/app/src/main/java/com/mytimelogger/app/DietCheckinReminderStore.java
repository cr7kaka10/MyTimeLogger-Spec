package com.mytimelogger.app;

import android.content.Context;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

final class DietCheckinReminderStore {
    static boolean needsReminder(Context context, long now) {
        if (!DietCheckinReminderSchedule.trainingDay(now)) return false;
        if (new WidgetTimerRuntimeStore(context).read() == null) return false;
        String name = new WidgetTimerPreferences(context).loadActiveDatabaseName();
        if (name == null || !context.getDatabasePath(name).isFile()) return false;
        SqliteConnection db = new SqliteConnection(context, name);
        try {
            db.open();
            List<Map<String, Object>> version = db.query(
                "SELECT value FROM system_config WHERE key='active_exercise_plan_version'", Arrays.asList());
            if (version.isEmpty() || !"v5".equals(String.valueOf(version.get(0).get("value")))) return false;
            List<Map<String, Object>> rows = db.query(
                "SELECT rule_key,status FROM exercise_diet_checkins WHERE date=? AND plan_version='v5' " +
                "AND rule_key IN ('no_sugary_drinks','no_refined_staples','no_snacks')",
                Arrays.asList(DailyWidgetStore.dayAt(now)));
            return shouldRemind(rows);
        } catch (RuntimeException error) {
            android.util.Log.w("DietReminder", "diet_state_unavailable", error);
            return false;
        } finally { db.close(); }
    }
    static boolean shouldRemind(List<Map<String, Object>> rows) {
        int processed = 0;
        for (Map<String, Object> row : rows) {
            String status = String.valueOf(row.get("status"));
            if ("completed".equals(status) || "failed".equals(status)) processed++;
        }
        return processed < 3;
    }
    private DietCheckinReminderStore() {}
}
