package com.mytimelogger.app;

import com.google.gson.JsonArray;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;

final class DailyWidgetSchedule {
    private DailyWidgetSchedule() {}
    static boolean scheduled(String rule, String day) {
        String value = rule == null ? "" : rule.replaceFirst("(?i)^RRULE:", "").toUpperCase(Locale.ROOT);
        if (value.isEmpty() || value.contains("FREQ=DAILY") || !value.contains("FREQ=WEEKLY")) return true;
        int start = value.indexOf("BYDAY=");
        if (start < 0) return true;
        String selected = value.substring(start + 6).split(";", 2)[0];
        SimpleDateFormat date = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        date.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
        date.setLenient(false);
        try {
            Date parsed = date.parse(day);
            if (parsed == null || !day.equals(date.format(parsed))) return true;
            SimpleDateFormat weekday = new SimpleDateFormat("EEE", Locale.US);
            weekday.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
            String code = weekday.format(parsed).substring(0, 2).toUpperCase(Locale.ROOT);
            return Arrays.asList(selected.split(",")).contains(code);
        } catch (Exception ignored) { return true; }
    }
    static JsonArray ids(android.content.Context context, String database, String day) {
        SqliteConnection db = new SqliteConnection(context, database);
        try {
            db.open();
            JsonArray ids = new JsonArray();
            List<Map<String, Object>> rows = db.query("SELECT id,repeat_rule FROM habits WHERE is_active=0 AND source='local' ORDER BY sort_order,id", Collections.emptyList());
            for (Map<String, Object> row : rows)
                if (scheduled((String) row.get("repeat_rule"), day)) ids.add(String.valueOf(row.get("id")));
            return ids;
        } finally { db.close(); }
    }
}
