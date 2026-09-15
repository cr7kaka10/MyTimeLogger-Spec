package com.mytimelogger.app;

import java.util.Collections;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public final class WidgetTimerEngine {
    public static final class Category {
        public final long id; public final String name; public final boolean active;
        public Category(long id, String name, boolean active) { this.id = id; this.name = name; this.active = active; }
    }
    public static final class Snapshot {
        public final String state; public final boolean paused; public final Long categoryId;
        public final String categoryName; public final long capturedAtEpochMs; public final long elapsedMs;
        public final Long startedAtEpochMs;
        public Snapshot(String state, boolean paused, Long categoryId, String categoryName,
                        long capturedAtEpochMs, long elapsedMs, Long startedAtEpochMs) {
            this.state = state; this.paused = paused; this.categoryId = categoryId; this.categoryName = categoryName;
            this.capturedAtEpochMs = capturedAtEpochMs; this.elapsedMs = elapsedMs; this.startedAtEpochMs = startedAtEpochMs;
        }
        public static Snapshot stopped(long capturedAtEpochMs) {
            return new Snapshot("stopped", false, null, "", capturedAtEpochMs, 0L, null);
        }
        public Map<String, Object> toCompatibleMap() {
            Map<String, Object> value = map(
                    "version", 1, "capturedAtEpochMs", capturedAtEpochMs, "state", state, "isPaused", paused,
                    "category", map("id", categoryId, "name", categoryName, "task", ""),
                    "pause", map("count", 0, "reasons", Collections.emptyList(), "startedAtEpochMs", null),
                    "segments", Collections.emptyList(),
                    "session", map("startedAtEpochMs", startedAtEpochMs, "largeStartedAtEpochMs", startedAtEpochMs,
                            "durationSeconds", 0, "totalStudySeconds", 0, "currentCycleStudySeconds", 0, "netDurationSeconds", 0),
                    "timing", map("mode", "countup_studying".equals(state) ? "countup" : "countdown",
                            "elapsedMs", elapsedMs, "deadlineEpochMs", null));
            return value;
        }
    }
    public static final class Session {
        public final long categoryId, startEpochMs, endEpochMs, durationSeconds;
        Session(long categoryId, long startEpochMs, long endEpochMs, long durationSeconds) {
            this.categoryId = categoryId; this.startEpochMs = startEpochMs;
            this.endEpochMs = endEpochMs; this.durationSeconds = durationSeconds;
        }
    }
    public static final class Result {
        public final String status; public final Snapshot snapshot; public final List<Session> sessions;
        Result(String status, Snapshot snapshot, List<Session> sessions) {
            this.status = status; this.snapshot = snapshot; this.sessions = sessions;
        }
    }

    public static Result apply(Snapshot before, WidgetTimerCommand command, Category target) {
        return apply(before, command, target, Collections.<String>emptySet());
    }

    public static Result apply(Snapshot before, WidgetTimerCommand command, Category target, Set<String> appliedIds) {
        if (appliedIds.contains(command.commandId)) return result("noop", before, Collections.<Session>emptyList());
        if (target == null || !target.active || target.id != command.categoryId
                || WidgetTimerCommand.isBlockedCategoryName(target.name))
            return new Result("requires_app", before, Collections.<Session>emptyList());
        if ("stopped".equals(before.state)) {
            if (!"start".equals(command.action)) return result("requires_app", before, Collections.<Session>emptyList());
            return result("applied", start(target, command.eventEpochMs), Collections.<Session>emptyList());
        }
        if (!"countup_studying".equals(before.state) || WidgetTimerCommand.isBlockedCategoryName(before.categoryName))
            return result("requires_app", before, Collections.<Session>emptyList());
        if (!"stop".equals(command.action) && before.categoryId != null && before.categoryId == target.id)
            return result("noop", before, Collections.<Session>emptyList());
        if (!("switch".equals(command.action) || "stop".equals(command.action)) || before.startedAtEpochMs == null
                || before.categoryId == null || ("stop".equals(command.action) && before.categoryId != target.id))
            return result("requires_app", before, Collections.<Session>emptyList());
        long at = command.eventEpochMs;
        long elapsed = before.elapsedMs + (before.paused ? 0L : Math.max(0L, at - before.capturedAtEpochMs));
        Session session = new Session(before.categoryId, before.startedAtEpochMs, at, elapsed / 1000L);
        Snapshot next = "switch".equals(command.action) ? start(target, at) : Snapshot.stopped(at);
        return result("applied", next, Collections.singletonList(session));
    }

    private static Snapshot start(Category target, long at) {
        return new Snapshot("countup_studying", false, target.id, target.name, at, 0L, at);
    }
    private static Result result(String status, Snapshot snapshot, List<Session> sessions) {
        return new Result(status, snapshot, sessions);
    }
    private static Map<String, Object> map(Object... pairs) {
        Map<String, Object> value = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) value.put((String) pairs[index], pairs[index + 1]);
        return value;
    }

    private WidgetTimerEngine() {}
}
