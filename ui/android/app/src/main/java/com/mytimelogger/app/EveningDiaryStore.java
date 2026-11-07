package com.mytimelogger.app;

import android.content.Context;
import java.util.Collections;
import java.util.List;
import java.util.Map;

final class EveningDiaryStore {
    static final String UNKNOWN="unknown", WAITING="waiting", READY="ready", WRITTEN="written";
    static String classify(Number status, String fullState, String diary) {
        if (diary != null && !diary.trim().isEmpty()) return WRITTEN;
        return status != null && status.intValue() >= 2 && "generated".equals(fullState) ? READY : WAITING;
    }
    static String today(Context context, String date) {
        if (new WidgetTimerRuntimeStore(context).read() == null) return UNKNOWN;
        String name = new WidgetTimerPreferences(context).loadActiveDatabaseName();
        if (name == null || !context.getDatabasePath(name).isFile()) return UNKNOWN;
        SqliteConnection db = new SqliteConnection(context, name);
        try {
            db.open();
            List<Map<String,Object>> rows = db.query("SELECT report_status,full_report_state,evening_diary FROM huawei_sleep_data WHERE date=? LIMIT 1", Collections.singletonList(date));
            if (rows.isEmpty()) return WAITING;
            Map<String,Object> row = rows.get(0);
            Object value = row.get("report_status");
            Number status = value instanceof Number ? (Number)value : null;
            return classify(status, (String)row.get("full_report_state"), (String)row.get("evening_diary"));
        } catch (RuntimeException error) { return UNKNOWN; }
        finally { db.close(); }
    }
    private EveningDiaryStore() {}
}
