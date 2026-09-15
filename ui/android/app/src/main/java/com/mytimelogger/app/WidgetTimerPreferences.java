package com.mytimelogger.app;

import android.content.Context;
import android.content.SharedPreferences;

public final class WidgetTimerPreferences {
    public interface Backend { String get(String key); void put(String key, String value); }
    static final String SNAPSHOT_KEY = "mtl.runtime.timer.logic.snapshot.v1";
    static final String COMMAND_KEY = "mtl.runtime.timer.widget.commands.v1";
    private final Backend backend;

    public WidgetTimerPreferences(Backend backend) { this.backend = backend; }
    public WidgetTimerPreferences(Context context) {
        final SharedPreferences preferences = context.getApplicationContext()
                .getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE);
        this.backend = new Backend() {
            public String get(String key) { return preferences.getString(key, null); }
            public void put(String key, String value) { preferences.edit().putString(key, value).apply(); }
        };
    }

    public String loadSnapshot() {
        String value = backend.get(SNAPSHOT_KEY);
        return isSnapshot(value) ? value : null;
    }
    public boolean saveSnapshot(String value) {
        if (!isSnapshot(value)) return false;
        backend.put(SNAPSHOT_KEY, value); return true;
    }
    public String loadCommandState() {
        String value = backend.get(COMMAND_KEY);
        return isObject(value) ? value : null;
    }
    public boolean saveCommandState(String value) {
        if (!isObject(value)) return false;
        backend.put(COMMAND_KEY, value); return true;
    }

    static final String ACTIVE_DB_KEY = "mtl.runtime.widget.active_database_name";

    /** 读取 WebView 写入的活跃数据库名，未设置时返回 null */
    public String loadActiveDatabaseName() {
        String value = backend.get(ACTIVE_DB_KEY);
        if (value == null || value.trim().isEmpty()) return null;
        String trimmed = value.trim();
        if (!trimmed.endsWith(".db")) return null;
        return trimmed;
    }

    private static boolean isSnapshot(String value) {
        if (!isObject(value) || !value.contains("\"version\":1")) return false;
        String[] fields = {"capturedAtEpochMs", "state", "isPaused", "category", "pause", "segments", "session", "timing"};
        for (String field : fields) if (!value.contains("\"" + field + "\"")) return false;
        return true;
    }
    private static boolean isObject(String value) {
        if (value == null) return false;
        String trimmed = value.trim();
        return trimmed.startsWith("{") && trimmed.endsWith("}");
    }
}
