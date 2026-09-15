package com.mytimelogger.app;

import android.content.Context;
import android.database.sqlite.SQLiteException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.UUID;
import java.text.SimpleDateFormat;

public final class WidgetTimerRepository {
    public static final String DATABASE_NAME = "my_time_logger.db";
    private static final String CATEGORY_SQL = "SELECT id, name, icon, color FROM categories "
            + "WHERE is_active = 1 ORDER BY sort_order, id";
    public interface QueryPort { List<Map<String, Object>> query(String sql, List<?> parameters); }
    public interface StoragePort extends QueryPort {
        void execute(String sql, List<?> parameters);
        void transaction(Runnable body);
    }
    public static final class Category {
        public final long id; public final String name, icon, color;
        Category(long id, String name, String icon, String color) {
            this.id = id; this.name = name; this.icon = icon; this.color = color;
        }
    }
    private final QueryPort queryPort;
    private final StoragePort storagePort;

    public WidgetTimerRepository(QueryPort queryPort) {
        this.queryPort = queryPort;
        this.storagePort = queryPort instanceof StoragePort ? (StoragePort) queryPort : null;
    }
    public WidgetTimerRepository(Context context) {
        String activeName = new WidgetTimerPreferences(context).loadActiveDatabaseName();
        String dbName = activeName != null ? activeName : DATABASE_NAME;
        final SqliteConnection connection = new SqliteConnection(context, dbName);
        connection.open();
        StoragePort port = new StoragePort() {
            public List<Map<String, Object>> query(String sql, List<?> parameters) {
                return connection.query(sql, parameters);
            }
            public void execute(String sql, List<?> parameters) { connection.execute(sql, parameters); }
            public void transaction(Runnable body) { connection.transaction(body::run); }
        };
        this.queryPort = port; this.storagePort = port;
    }

    public List<Category> loadCategories() {
        List<Category> categories = new ArrayList<>();
        final List<Map<String, Object>> rows;
        try { rows = queryPort.query(CATEGORY_SQL, Collections.emptyList()); }
        catch (SQLiteException unavailable) {
            String message = unavailable.getMessage();
            if (message != null && message.contains("no such table") && message.contains("categories"))
                return Collections.emptyList();
            throw unavailable;
        }
        for (Map<String, Object> row : rows) {
            categories.add(new Category(number(row.get("id")), text(row.get("name")),
                    text(row.get("icon")), text(row.get("color"))));
        }
        return categories;
    }

    public void saveSession(WidgetTimerEngine.Session session) {
        if (storagePort == null) throw new IllegalStateException("session-storage-unavailable");
        TimeZone beijing = TimeZone.getTimeZone("Asia/Shanghai");
        SimpleDateFormat timestamp = format("yyyy-MM-dd HH:mm:ss", beijing);
        SimpleDateFormat date = format("yyyy-MM-dd", beijing);
        SimpleDateFormat day = format("EEEE", beijing);
        Date end = new Date(session.endEpochMs);
        List<Object> values = Arrays.<Object>asList(UUID.randomUUID().toString(),
                timestamp.format(new Date(session.startEpochMs)), timestamp.format(end),
                session.durationSeconds / 60d, session.durationSeconds, date.format(end), day.format(end),
                0, "无", "", session.categoryId, timestamp.format(end), null);
        String sql = "INSERT INTO study_sessions (id,start_time,end_time,net_duration_minutes,net_duration_seconds,date,day_of_week,"
                + "pause_count,pause_reasons,session_summary,category_id,updated_at,pushed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)";
        storagePort.transaction(() -> storagePort.execute(sql, values));
    }

    public void recordBehavior(String action, String result, long occurredAt) {
        recordBehavior(UUID.randomUUID().toString(), action, result, occurredAt);
    }

    public void recordBehavior(String eventId, String action, String result, long occurredAt) {
        if (storagePort == null) return;
        TimeZone zone = TimeZone.getTimeZone("Asia/Shanghai");
        String stamp = format("yyyy-MM-dd HH:mm:ss", zone).format(new Date(occurredAt));
        storagePort.execute("CREATE TABLE IF NOT EXISTS behavior_event_outbox (event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, device_id TEXT NOT NULL, runtime TEXT NOT NULL, page TEXT NOT NULL, event_type TEXT NOT NULL, action TEXT NOT NULL, target_type TEXT, target_id TEXT, result TEXT NOT NULL, error_code TEXT, trace_id TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', priority TEXT NOT NULL DEFAULT 'normal', created_at TEXT NOT NULL)", Collections.emptyList());
        storagePort.execute("INSERT OR IGNORE INTO behavior_event_outbox (event_id,occurred_at,device_id,runtime,page,event_type,action,result,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", Arrays.<Object>asList(eventId, stamp, "android-widget", "capacitor-android", "widget", "widget", action, result, "{}", stamp));
    }

    static boolean acceptsRevision(long currentRevision, long incomingRevision) {
        return incomingRevision >= currentRevision;
    }

    private static SimpleDateFormat format(String pattern, TimeZone zone) {
        SimpleDateFormat value = new SimpleDateFormat(pattern, Locale.CHINA); value.setTimeZone(zone); return value;
    }

    private static long number(Object value) { return ((Number) value).longValue(); }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }
    static String categorySqlForTest() { return CATEGORY_SQL; }
}
