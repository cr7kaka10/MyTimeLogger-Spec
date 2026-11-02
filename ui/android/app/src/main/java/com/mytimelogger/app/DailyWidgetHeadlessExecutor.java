package com.mytimelogger.app;

import android.content.Context;
import com.google.gson.JsonObject;

final class DailyWidgetHeadlessExecutor {
    static final class Outcome {
        final String status, message;
        Outcome(String status, String message) { this.status = status; this.message = message; }
    }

    static boolean valid(JsonObject snapshot, JsonObject command, String day) {
        if (!DailyWidgetStore.matchesCommand(snapshot, command, day)) return false;
        try {
            String kind = command.get("kind").getAsString();
            String action = command.has("action") ? command.get("action").getAsString() : "complete";
            String id = command.get("id").getAsString();
            return id.matches("[A-Za-z0-9._:-]{1,128}")
                    && ("complete".equals(action) || ("habit".equals(kind) && "fail".equals(action)))
                    && ("task".equals(kind) || "habit".equals(kind));
        } catch (RuntimeException ignored) { return false; }
    }

    static boolean validJournal(JsonObject snapshot, JsonObject command, String commandId, String day) {
        if (commandId == null || !commandId.matches("[A-Za-z0-9._:-]{1,128}")) return false;
        try {
            return commandId.equals(command.get("commandId").getAsString())
                    && "habit".equals(command.get("kind").getAsString())
                    && "complete".equals(command.get("action").getAsString())
                    && valid(snapshot, command, day);
        } catch (RuntimeException ignored) { return false; }
    }

    static Outcome run(Context context, JsonObject command) {
        DailyWidgetStore store = new DailyWidgetStore(context);
        JsonObject snapshot = store.snapshot();
        if (!valid(snapshot, command, DailyWidgetStore.today())) return new Outcome("rejected", "清单已过期，请刷新");
        WidgetTimerRuntimeStore.Config runtime = new WidgetTimerRuntimeStore(context).read();
        if (runtime == null || !runtime.verifiedUserId.equals(snapshot.get("userId").getAsString())
                || runtime.generation != snapshot.get("generation").getAsLong())
            return new Outcome("rejected", "登录状态已变化，请刷新");
        if ("habit".equals(command.get("kind").getAsString())) {
            boolean eligible = false;
            for (DailyWidgetRepository.Row row : new DailyWidgetRepository(context).load())
                if (!row.header && "habit".equals(row.kind) && row.id.equals(command.get("id").getAsString()) && row.blocked.isEmpty()) {
                    eligible = true; break;
                }
            if (!eligible) return new Outcome("rejected", "习惯状态已变化，请刷新");
            String result = new DailyWidgetHabitClient().apply(runtime, command);
            if ("applied".equals(result)) return new Outcome("applied", "习惯已记录");
            if ("already_complete".equals(result)) return new Outcome("rejected", "习惯今天已完成");
            if ("unauthorized".equals(result)) return new Outcome("failed", "登录已失效，请打开 App 重新登录");
            if ("retryable".equals(result)) return new Outcome("failed", "网络未确认，点击可重试");
            return new Outcome("rejected", "习惯操作被拒绝，请刷新后重试");
        }
        String result = DailyWidgetTaskWriter.complete(context, snapshot.get("database").getAsString(),
                command.get("id").getAsString());
        if ("applied".equals(result)) return new Outcome("applied", "任务已完成");
        if ("pending_sync".equals(result)) return new Outcome("pending_sync", "任务已完成，等待同步");
        return new Outcome("failed", "任务未完成，点击可重试");
    }
}
