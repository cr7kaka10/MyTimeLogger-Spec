package com.mytimelogger.app;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class WidgetCommandStore {
    private static final Pattern STORED = Pattern.compile("\\{\\\"commandId\\\":\\\"([A-Za-z0-9._:-]{1,64})\\\","
            + "\\\"applied\\\":(true|false),\\\"result\\\":\\\"(claimed|pending|unknown|applied|headless-applied|requires_app|failed)\\\"\\}");
    public static final class Entry {
        public final boolean newlyClaimed;
        public final boolean applied;
        public final String result;
        private Entry(boolean newlyClaimed, boolean applied, String result) {
            this.newlyClaimed = newlyClaimed; this.applied = applied; this.result = result;
        }
    }

    private final int limit;
    private final WidgetTimerPreferences.Backend backend;
    private final LinkedHashMap<String, Entry> entries = new LinkedHashMap<>();

    public WidgetCommandStore(int limit) { this(null, limit); }
    public WidgetCommandStore(WidgetTimerPreferences.Backend backend, int limit) {
        if (limit < 1) throw new IllegalArgumentException("invalid-limit");
        this.backend = backend; this.limit = limit;
        if (backend != null) restore(backend.get(WidgetTimerPreferences.COMMAND_KEY));
    }

    public synchronized Entry claim(String commandId) {
        Entry existing = entries.get(commandId);
        if (existing != null) return existing;
        Entry stored = new Entry(false, false, "claimed");
        entries.put(commandId, stored);
        trim();
        persist();
        return new Entry(true, false, "claimed");
    }

    public synchronized Entry markApplied(String commandId, String result) {
        return mark(commandId, result, true);
    }

    public synchronized Entry mark(String commandId, String result, boolean applied) {
        if (!entries.containsKey(commandId)) throw new IllegalStateException("command-not-claimed");
        if (!result.matches("claimed|pending|unknown|applied|headless-applied|requires_app|failed")) throw new IllegalArgumentException("invalid-result");
        Entry value = new Entry(false, applied, result);
        entries.put(commandId, value);
        persist();
        return value;
    }

    public synchronized Entry get(String commandId) { return entries.get(commandId); }
    public synchronized int size() { return entries.size(); }

    private void trim() {
        while (entries.size() > limit) {
            String oldest = entries.entrySet().iterator().next().getKey();
            entries.remove(oldest);
        }
    }
    private void restore(String raw) {
        if (raw == null) return;
        Matcher matcher = STORED.matcher(raw);
        while (matcher.find()) entries.put(matcher.group(1), new Entry(false,
                Boolean.parseBoolean(matcher.group(2)), matcher.group(3)));
        trim();
    }
    private void persist() {
        if (backend == null) return;
        StringBuilder json = new StringBuilder("{\"entries\":[");
        int index = 0;
        for (Map.Entry<String, Entry> item : entries.entrySet()) {
            if (index++ > 0) json.append(',');
            Entry value = item.getValue();
            json.append("{\"commandId\":\"").append(item.getKey()).append("\",\"applied\":")
                    .append(value.applied).append(",\"result\":\"").append(value.result).append("\"}");
        }
        backend.put(WidgetTimerPreferences.COMMAND_KEY, json.append("]}").toString());
    }
}
