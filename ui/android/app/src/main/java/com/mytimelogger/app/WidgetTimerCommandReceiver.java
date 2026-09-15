package com.mytimelogger.app;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.Toast;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;

public final class WidgetTimerCommandReceiver extends BroadcastReceiver {
    public static final String ACTION = "com.mytimelogger.app.TIMER_WIDGET_COMMAND";
    public static final String ACTION_REFRESH = "com.mytimelogger.app.TIMER_WIDGET_REFRESH";
    static final String ACTION_OPEN_AI_PROMPT = "open_ai_prompt";
    private static final HashSet<String> FIELDS = new HashSet<>(Arrays.asList("action", "commandId", "categoryId", "eventEpochMs"));
    interface LivePort {
        boolean dispatch(WidgetTimerCommand command);
        String awaitAck(String commandId);
    }
    interface Fallback { String apply(); }
    private static final Object RUNTIME_LOCK = new Object();

    static final class PendingIntentSpec {
        final String packageName;
        final String componentClassName;
        final int requestCode;
        final int flags;
        final Map<String, Object> extras;

        PendingIntentSpec(String packageName, int requestCode, int flags, Map<String, Object> extras) {
            this.packageName = packageName;
            this.componentClassName = WidgetTimerCommandReceiver.class.getName();
            this.requestCode = requestCode;
            this.flags = flags;
            this.extras = extras;
        }
    }

    static PendingIntentSpec pendingIntentSpec(String packageName, WidgetTimerCommand command) {
        Map<String, Object> extras = new LinkedHashMap<>();
        extras.put("action", command.action); extras.put("commandId", command.commandId);
        extras.put("categoryId", command.categoryId); extras.put("eventEpochMs", command.eventEpochMs);
        return new PendingIntentSpec(packageName, requestCode(command.commandId),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE, extras);
    }

    static PendingIntentSpec collectionTemplateSpec(String packageName, int requestCode) {
        return new PendingIntentSpec(packageName, requestCode,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE, new LinkedHashMap<>());
    }

    static PendingIntent collectionTemplate(Context context, int requestCode) {
        PendingIntentSpec spec = collectionTemplateSpec(context.getPackageName(), requestCode);
        Intent intent = new Intent(ACTION).setPackage(spec.packageName)
                .setClass(context, WidgetTimerCommandReceiver.class);
        return PendingIntent.getBroadcast(context, spec.requestCode, intent, spec.flags);
    }

    static PendingIntentSpec refreshPendingIntentSpec(String packageName) {
        return new PendingIntentSpec(packageName, 0x4d5452,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE, new LinkedHashMap<>());
    }

    static PendingIntent refreshPendingIntent(Context context) {
        PendingIntentSpec spec = refreshPendingIntentSpec(context.getPackageName());
        Intent intent = new Intent(ACTION_REFRESH).setPackage(spec.packageName)
                .setClass(context, WidgetTimerCommandReceiver.class);
        return PendingIntent.getBroadcast(context, spec.requestCode, intent, spec.flags);
    }

    static PendingIntent stopPendingIntent(Context context, long categoryId) {
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("action", "stop"); raw.put("commandId", "widget-stop-" + Long.toHexString(System.nanoTime()));
        raw.put("categoryId", categoryId); raw.put("eventEpochMs", System.currentTimeMillis());
        return pendingIntent(context, WidgetTimerCommand.parse(raw));
    }

    static Map<String, Object> receivedRaw(Map<String, Object> extras, long receivedAtEpochMs) {
        Map<String, Object> value = new LinkedHashMap<>(extras);
        value.put("eventEpochMs", receivedAtEpochMs);
        return value;
    }

    static int requestCode(String commandId) { return commandId.hashCode() & 0x7fffffff; }

    static PendingIntent pendingIntent(Context context, WidgetTimerCommand command) {
        PendingIntentSpec spec = pendingIntentSpec(context.getPackageName(), command);
        Intent intent = new Intent(ACTION).setPackage(spec.packageName)
                .setClass(context, WidgetTimerCommandReceiver.class)
                .putExtra("action", command.action).putExtra("commandId", command.commandId)
                .putExtra("categoryId", command.categoryId).putExtra("eventEpochMs", command.eventEpochMs);
        return PendingIntent.getBroadcast(context, spec.requestCode, intent, spec.flags);
    }

    @Override public void onReceive(Context context, Intent intent) {
        if (intent == null || !context.getPackageName().equals(intent.getPackage())
                || intent.getComponent() == null
                || !WidgetTimerCommandReceiver.class.getName().equals(intent.getComponent().getClassName())) return;
        if (ACTION_REFRESH.equals(intent.getAction())) {
            if (intent.getExtras() != null && !intent.getExtras().isEmpty()) return;
            PendingResult pending = goAsync();
            Context app = context.getApplicationContext();
            new Thread(() -> {
                try { refreshRuntime(app); }
                finally { pending.finish(); }
            }, "timer-widget-refresh").start();
            return;
        }
        if (!ACTION.equals(intent.getAction()) || intent.getExtras() == null
                || !intent.getExtras().keySet().equals(FIELDS)) return;
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("action", intent.getStringExtra("action"));
        raw.put("commandId", intent.getStringExtra("commandId"));
        raw.put("categoryId", intent.getLongExtra("categoryId", 0));
        raw.put("eventEpochMs", intent.getLongExtra("eventEpochMs", 0));
        if (ACTION_OPEN_AI_PROMPT.equals(raw.get("action")) && ((Long) raw.get("categoryId")) == 0L) {
            context.startActivity(TimerWidgetProvider.openTimerAiIntent(context)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            return;
        }
        raw = receivedRaw(raw, System.currentTimeMillis());
        try {
            WidgetTimerCommand command = WidgetTimerCommand.parse(raw);
            PendingResult pending = goAsync();
            Context app = context.getApplicationContext();
            new Thread(() -> {
                try {
                    applyRuntime(app, command);
                    app.sendBroadcast(new Intent(TimerWidgetProvider.ACTION_COMMAND_APPLIED)
                            .setPackage(app.getPackageName()).setClass(app, TimerWidgetProvider.class));
                } finally { pending.finish(); }
            }, "timer-widget-command").start();
        } catch (IllegalArgumentException ignored) { }
    }

    private static void refreshRuntime(Context context) {
        WidgetTimerRuntimeStore.Config runtime = new WidgetTimerRuntimeStore(context).read();
        WidgetTimerApiClient.Outcome outcome = new WidgetTimerApiClient().readCurrentState(runtime);
        Log.i("TimerWidgetRefresh", "authoritative_read_status=" + outcome.status);
        if (persistRefresh(outcome, new WidgetTimerPreferences(context), System.currentTimeMillis())) {
            WidgetTimerBridge active = WidgetTimerBridge.current();
            if (active != null) active.authoritativeStateChanged();
            context.sendBroadcast(new Intent(TimerWidgetProvider.ACTION_COMMAND_APPLIED)
                    .setPackage(context.getPackageName()).setClass(context, TimerWidgetProvider.class));
            return;
        }
        notifyFailure(context, "unauthorized".equals(outcome.status)
                ? "登录已失效，请打开 App 重新登录" : "同步失败，已保留当前计时状态");
    }

    static boolean persistRefresh(WidgetTimerApiClient.Outcome outcome,
            WidgetTimerPreferences preferences, long capturedAt) {
        if (outcome == null || !outcome.applied()) return false;
        String snapshot = WidgetTimerAuthoritativeSnapshotMapper.map(outcome.state, capturedAt);
        return snapshot != null && preferences.saveSnapshot(snapshot);
    }

    private static String applyRuntime(Context context, WidgetTimerCommand command) {
        synchronized (RUNTIME_LOCK) { return applyRuntimeLocked(context, command); }
    }

    private static String applyRuntimeLocked(Context context, WidgetTimerCommand command) {
        WidgetTimerPreferences.Backend backend = backend(context);
        WidgetCommandStore store = new WidgetCommandStore(backend, 128);
        WidgetCommandStore.Entry claim = store.claim(command.commandId);
        if (!claim.newlyClaimed) {
            if (claim.applied || "pending".equals(claim.result)) return claim.result;
            if (!"unknown".equals(claim.result)) return "failed";
            store.mark(command.commandId, "pending", false);
        }
        try { new WidgetTimerRepository(context).recordBehavior(command.commandId, "widget.timer_command", "accepted", command.eventEpochMs); } catch (RuntimeException ignored) { }
        WidgetTimerRepository repository = new WidgetTimerRepository(context);
        String targetName = null;
        for (WidgetTimerRepository.Category item : repository.loadCategories()) {
            if (item.id == command.categoryId) {
                targetName = item.name; break;
            }
        }
        if (targetName == null || WidgetTimerCommand.isBlockedCategoryName(targetName)) {
            store.mark(command.commandId, "requires_app", false); notifyFailure(context, "此分类请在 App 内计时"); return "requires_app";
        }
        WidgetTimerBridge bridge = WidgetTimerBridge.current();
        if (bridge != null && bridge.dispatch(command, targetName)) {
            store.mark(command.commandId, "pending", false);
            for (int attempt = 0; attempt < 20; attempt++) {
                String ack = bridge.ackResult(command.commandId);
                if (validResult(ack)) { store.mark(command.commandId, ack, "applied".equals(ack)); return ack; }
                try { Thread.sleep(25L); } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt(); break;
                }
            }
        }
        WidgetTimerRuntimeStore.Config runtime = new WidgetTimerRuntimeStore(context).read();
        WidgetTimerApiClient.Outcome outcome = new WidgetTimerApiClient().execute(runtime, command, targetName);
        if ("applied".equals(persistHeadless(outcome, new WidgetTimerPreferences(context), store, command.commandId, System.currentTimeMillis()))) {
            WidgetTimerBridge active = WidgetTimerBridge.current(); if (active != null) active.authoritativeStateChanged();
            return "applied";
        }
        WidgetTimerBridge active = WidgetTimerBridge.current();
        String lateAck = active == null ? null : active.ackResult(command.commandId);
        if (validResult(lateAck)) { store.mark(command.commandId, lateAck, "applied".equals(lateAck)); return lateAck; }
        notifyFailure(context, "unauthorized".equals(outcome.status) ? "登录已失效，请打开 App 重新登录" : "计时失败，请检查网络"); return "failed";
    }

    static String persistHeadless(WidgetTimerApiClient.Outcome outcome, WidgetTimerPreferences preferences,
            WidgetCommandStore store, String commandId, long capturedAt) {
        if (outcome != null && outcome.applied()) {
            String snapshot = WidgetTimerAuthoritativeSnapshotMapper.map(outcome.state, capturedAt);
            if (snapshot != null && preferences.saveSnapshot(snapshot)) { store.mark(commandId, "headless-applied", true); return "applied"; }
        }
        store.mark(commandId, "failed", false); return "failed";
    }

    private static void notifyFailure(Context context, String message) {
        new Handler(Looper.getMainLooper()).post(() -> Toast.makeText(context, message, Toast.LENGTH_SHORT).show());
    }

    private static WidgetTimerPreferences.Backend backend(Context context) {
        SharedPreferences values = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE);
        return new WidgetTimerPreferences.Backend() {
            public String get(String key) { return values.getString(key, null); }
            public void put(String key, String value) { values.edit().putString(key, value).apply(); }
        };
    }

    static String coordinate(WidgetTimerCommand command, WidgetCommandStore store,
            LivePort live, Fallback fallback) {
        WidgetCommandStore.Entry claim = store.claim(command.commandId);
        if (!claim.newlyClaimed) {
            if (claim.applied || "pending".equals(claim.result)) return claim.result;
            if (!"unknown".equals(claim.result)) return "failed";
            store.mark(command.commandId, "pending", false);
        }
        if (live != null && live.dispatch(command)) {
            store.mark(command.commandId, "pending", false);
            String ack = live.awaitAck(command.commandId);
            if (validResult(ack)) {
                store.mark(command.commandId, ack, "applied".equals(ack));
                return ack;
            }
            WidgetCommandStore.Entry late = store.get(command.commandId);
            if (late != null && late.applied) return late.result;
        }
        synchronized (store) {
            WidgetCommandStore.Entry afterTimeout = store.get(command.commandId);
            if (afterTimeout != null && afterTimeout.applied) return afterTimeout.result;
            String result = fallback.apply();
            WidgetCommandStore.Entry afterFallback = store.get(command.commandId);
            if (afterFallback != null && afterFallback.applied) return afterFallback.result;
            result = validResult(result) ? result : "failed";
            store.mark(command.commandId, result, "applied".equals(result));
            return result;
        }
    }
    private static boolean validResult(String result) {
        return "applied".equals(result) || "requires_app".equals(result) || "failed".equals(result);
    }
}
