package com.mytimelogger.app;

import android.content.Context;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class DailyWidgetRepository {
    static final class Row {
        final String kind, id, title, badge, day;
        final boolean checked, header;
        Row(String kind, String id, String title, String badge, String day, boolean checked, boolean header) {
            this.kind = kind; this.id = id; this.title = title; this.badge = badge;
            this.day = day; this.checked = checked; this.header = header;
        }
    }
    static Row header(String title, String badge) { return new Row("header", "", title, badge, "", false, true); }
    private final Context context;
    DailyWidgetRepository(Context context) { this.context = context.getApplicationContext(); }
    List<Row> load() {
        DailyWidgetStore store = new DailyWidgetStore(context);
        JsonObject snapshot = store.snapshot();
        if (snapshot == null) return Collections.singletonList(header("打开 App 刷新今日清单", ""));
        String today = DailyWidgetStore.today();
        Set<String> scheduled = new HashSet<>();
        JsonArray ids = snapshot.getAsJsonObject("days").getAsJsonArray(today);
        for (JsonElement id : ids) scheduled.add(id.getAsString());
        SqliteConnection db = new SqliteConnection(context, snapshot.get("database").getAsString());
        try {
            db.open();
            Map<String, Integer> checkins = new HashMap<>();
            for (Map<String, Object> item : db.query("SELECT habit_id,status FROM habit_checkins WHERE checkin_date=?", Collections.singletonList(today)))
                checkins.put(text(item.get("habit_id")), ((Number) item.get("status")).intValue());
            List<Row> result = new ArrayList<>();
            List<Row> habits = new ArrayList<>();
            for (Map<String, Object> item : db.query("SELECT id,name FROM habits WHERE is_active=0 AND source='local' ORDER BY sort_order,id", Collections.emptyList())) {
                String id = text(item.get("id"));
                if (includeHabit(scheduled, checkins, id))
                    habits.add(new Row("habit", id, text(item.get("name")), "习惯", today,
                            checkins.getOrDefault(id, 0) == 2 || store.isDone("habit", id, today), false));
            }
            if (!habits.isEmpty()) { result.add(header("今日习惯", String.valueOf(habits.size()))); result.addAll(habits); }
            List<Row> dueToday = new ArrayList<>(), overdue = new ArrayList<>();
            for (Map<String, Object> item : db.query("SELECT id,title,due_date FROM tasks WHERE status=0 AND deleted_at IS NULL "
                    + "AND due_date IS NOT NULL AND due_date<>'' AND substr(due_date,1,10)<=? ORDER BY due_date,priority DESC,id", Collections.singletonList(today))) {
                String id = text(item.get("id")), due = text(item.get("due_date"));
                if (due.length() < 10 || store.isDone("task", id, today)) continue;
                boolean late = dueBucket(due, today) < 0;
                Row row = new Row("task", id, text(item.get("title")), late ? due.substring(5, 10) : "今天", today, false, false);
                (late ? overdue : dueToday).add(row);
            }
            if (!dueToday.isEmpty()) { result.add(header("今日任务", String.valueOf(dueToday.size()))); result.addAll(dueToday); }
            if (!overdue.isEmpty()) { result.add(header("已过期", String.valueOf(overdue.size()))); result.addAll(overdue); }
            if (result.isEmpty()) result.add(header("今天已完成", "暂无待办"));
            return result;
        } catch (RuntimeException error) {
            return Collections.singletonList(header("清单读取失败", "打开 App 检查"));
        } finally { db.close(); }
    }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }
    static int dueBucket(String due, String today) {
        if (due == null || due.length() < 10 || today == null) return 1;
        return Integer.signum(due.substring(0, 10).compareTo(today));
    }
    static boolean includeHabit(Set<String> scheduled, Map<String, Integer> checkins, String id) {
        return scheduled.contains(id) || checkins.containsKey(id);
    }
}
