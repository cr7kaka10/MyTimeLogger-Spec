package com.mytimelogger.app;
import java.util.regex.*;
final class WidgetTimerSnapshotParser {
    static final class Parsed {
        final WidgetTimerEngine.Snapshot snapshot;
        final String note;
        Parsed(WidgetTimerEngine.Snapshot snapshot, String note) { this.snapshot = snapshot; this.note = note; }
    }
    static Parsed parse(String json) {
        try {
            if (number(json, "version", null) != 1L) return null;
            String category = object(json, "category");
            String session = object(json, "session");
            String timing = object(json, "timing");
            String state = text(json, "state");
            Long captured = number(json, "capturedAtEpochMs", null);
            Long elapsed = number(timing, "elapsedMs", null);
            if (category == null || session == null || timing == null || state == null
                    || captured == null || elapsed == null) return null;
            WidgetTimerEngine.Snapshot snapshot = new WidgetTimerEngine.Snapshot(state,
                    bool(json, "isPaused"), number(category, "id", null), text(category, "name"),
                    captured, elapsed, number(session, "startedAtEpochMs", null));
            String note = text(category, "task");
            return new Parsed(snapshot, note == null ? "" : note);
        } catch (RuntimeException invalid) { return null; }
    }
    private static String object(String json, String key) {
        if (json == null) return null;
        Matcher match = Pattern.compile("\\\"" + Pattern.quote(key) + "\\\"\\s*:\\s*\\{([^{}]*)\\}")
                .matcher(json);
        return match.find() ? match.group(1) : null;
    }
    private static String raw(String json, String key) {
        if (json == null) return null;
        Matcher match = Pattern.compile("\\\"" + Pattern.quote(key) + "\\\"\\s*:\\s*"
                + "(null|true|false|-?\\d+|\\\"(?:\\\\.|[^\\\"\\\\])*\\\")").matcher(json);
        return match.find() ? match.group(1) : null;
    }
    private static Long number(String json, String key, Long fallback) {
        String value = raw(json, key); return value == null || "null".equals(value) ? fallback : Long.valueOf(value);
    }
    private static boolean bool(String json, String key) { return "true".equals(raw(json, key)); }
    private static String text(String json, String key) {
        String value = raw(json, key);
        return value == null || "null".equals(value) ? null
                : value.substring(1, value.length() - 1).replace("\\\"", "\"").replace("\\\\", "\\");
    }
    private WidgetTimerSnapshotParser() {}
}
