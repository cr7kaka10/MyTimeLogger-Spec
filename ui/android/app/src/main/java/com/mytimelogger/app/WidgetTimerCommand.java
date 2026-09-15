package com.mytimelogger.app;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class WidgetTimerCommand {
    private static final Set<String> ACTIONS = new HashSet<>(Arrays.asList("start", "switch", "stop"));
    private static final Set<String> FIELDS = new HashSet<>(Arrays.asList("action", "commandId", "categoryId", "eventEpochMs"));
    private static final Pattern COMMAND_ID = Pattern.compile("^[A-Za-z0-9._:-]{1,64}$");
    private static final long MAX_SAFE_INTEGER = 9007199254740991L;
    public final String action;
    public final String commandId;
    public final long categoryId;
    public final long eventEpochMs;

    private WidgetTimerCommand(String action, String commandId, long categoryId, long eventEpochMs) {
        this.action = action; this.commandId = commandId;
        this.categoryId = categoryId; this.eventEpochMs = eventEpochMs;
    }

    public static WidgetTimerCommand parse(Map<String, ?> value) {
        if (value == null || !value.keySet().equals(FIELDS)) throw invalid();
        Object action = value.get("action"), commandId = value.get("commandId");
        long categoryId = positiveInteger(value.get("categoryId"));
        long eventEpochMs = positiveInteger(value.get("eventEpochMs"));
        if (!(action instanceof String) || !ACTIONS.contains(action)) throw invalid();
        if (!(commandId instanceof String) || !COMMAND_ID.matcher((String) commandId).matches()) throw invalid();
        return new WidgetTimerCommand((String) action, (String) commandId, categoryId, eventEpochMs);
    }

    public static boolean isBlockedCategoryName(String name) {
        return "输入".equals(name) || "输出".equals(name);
    }

    private static long positiveInteger(Object value) {
        if (!(value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long)) throw invalid();
        long parsed = ((Number) value).longValue();
        if (parsed <= 0 || parsed > MAX_SAFE_INTEGER) throw invalid();
        return parsed;
    }

    private static IllegalArgumentException invalid() { return new IllegalArgumentException("invalid-command"); }
}
