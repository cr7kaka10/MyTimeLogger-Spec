package com.mytimelogger.app;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class WidgetIntegrationJournal {
    static final String KEY = "mtl.runtime.timer.widget.integration-journal.v1";
    private static final Pattern EVENT = Pattern.compile("\\{\\\"commandId\\\":\\\"([A-Za-z0-9._:-]{1,64})\\\",\\\"action\\\":\\\"(start|switch|stop)\\\",\\\"categoryId\\\":([1-9][0-9]*),\\\"eventEpochMs\\\":([1-9][0-9]*)\\}");
    public static final class Event {
        public final String commandId, action;
        public final long categoryId, eventEpochMs;
        Event(String commandId, String action, long categoryId, long eventEpochMs) {
            this.commandId = commandId; this.action = action;
            this.categoryId = categoryId; this.eventEpochMs = eventEpochMs;
        }
        String json() { return "{\"commandId\":\"" + commandId + "\",\"action\":\"" + action
                + "\",\"categoryId\":" + categoryId + ",\"eventEpochMs\":" + eventEpochMs + "}"; }
    }
    private final WidgetTimerPreferences.Backend backend;
    private final int limit;
    private final List<Event> events = new ArrayList<>();

    public WidgetIntegrationJournal(WidgetTimerPreferences.Backend backend, int limit) {
        if (limit < 1) throw new IllegalArgumentException("invalid-limit");
        this.backend = backend; this.limit = limit; restore(backend.get(KEY));
    }
    public synchronized boolean append(WidgetTimerCommand command) {
        for (Event event : events) if (event.commandId.equals(command.commandId)) return false;
        events.add(new Event(command.commandId, command.action, command.categoryId, command.eventEpochMs));
        while (events.size() > limit) events.remove(0);
        backend.put(KEY, rawJson()); return true;
    }
    public synchronized List<Event> events() { return Collections.unmodifiableList(new ArrayList<>(events)); }
    public synchronized String rawJson() {
        StringBuilder json = new StringBuilder("[");
        for (int index = 0; index < events.size(); index++) {
            if (index > 0) json.append(','); json.append(events.get(index).json());
        }
        return json.append(']').toString();
    }
    private void restore(String raw) {
        if (raw == null) return;
        Matcher matcher = EVENT.matcher(raw);
        while (matcher.find()) events.add(new Event(matcher.group(1), matcher.group(2),
                Long.parseLong(matcher.group(3)), Long.parseLong(matcher.group(4))));
        while (events.size() > limit) events.remove(0);
    }
}
