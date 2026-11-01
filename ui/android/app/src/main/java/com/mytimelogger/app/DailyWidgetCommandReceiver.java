package com.mytimelogger.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;
import com.google.gson.JsonObject;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

public final class DailyWidgetCommandReceiver extends BroadcastReceiver {
    static final String ACTION = "com.mytimelogger.app.DAILY_WIDGET_COMMAND";
    private static final Set<String> IN_FLIGHT = Collections.synchronizedSet(new HashSet<>());
    @Override public void onReceive(Context context, Intent intent) {
        if (intent == null || !ACTION.equals(intent.getAction())
                || !context.getPackageName().equals(intent.getPackage())
                || intent.getComponent() == null
                || !getClass().getName().equals(intent.getComponent().getClassName())) return;
        String action = intent.getStringExtra("action");
        if ("open".equals(action)) { openChecklist(context); return; }
        if ("toggle_items".equals(action)) {
            String id = intent.getStringExtra("id"), day = intent.getStringExtra("date");
            if (id == null || day == null || !day.equals(DailyWidgetStore.today())) return;
            for (DailyWidgetRepository.Row row : new DailyWidgetRepository(context).load()) {
                if ("task".equals(row.kind) && row.id.equals(id) && row.day.equals(day)
                        && !row.progress.isEmpty()) {
                    if (new DailyWidgetStore(context).toggleItems(id, day)) DailyWidgetProvider.refresh(context);
                    return;
                }
            }
            return;
        }
        if (!("complete".equals(action) || "menu_open".equals(action)
                || "menu_cancel".equals(action) || "menu_confirm".equals(action) || "menu_ignore".equals(action))) return;
        String kind = intent.getStringExtra("kind"), id = intent.getStringExtra("id");
        String day = intent.getStringExtra("date");
        if (kind == null || id == null || day == null || !day.equals(DailyWidgetStore.today())
                || (!"complete".equals(action) && !"habit".equals(kind))) return;
        DailyWidgetStore store = new DailyWidgetStore(context);
        if ("menu_cancel".equals(action)) {
            store.consumeMenu(id, day);
            DailyWidgetProvider.refresh(context);
            return;
        }
        if ("menu_confirm".equals(action) && !store.consumeMenu(id, day)) return;
        boolean eligible = false;
        for (DailyWidgetRepository.Row row : new DailyWidgetRepository(context).load())
            if (!row.header && !row.checked && row.kind.equals(kind) && row.id.equals(id) && row.day.equals(day)
                    && (row.blocked.isEmpty() || "menu_cancel".equals(action))
                    && (!"menu_ignore".equals(action) || !row.timed)) {
                eligible = true; break;
            }
        if (!eligible) return;
        if ("menu_ignore".equals(action)) {
            if (store.ignoreHabit(id, day)) { store.clearMenu(); DailyWidgetProvider.refresh(context); retryPendingIgnore(context); }
            return;
        }
        if ("menu_open".equals(action)) {
            if (store.openMenu(id, day)) DailyWidgetProvider.refresh(context);
            return;
        }
        if ("complete".equals(action)) store.clearMenu();
        JsonObject command = store.claim(kind, id, day,
                "menu_confirm".equals(action) ? "fail" : "complete");
        if (command == null) return;
        DailyWidgetProvider.refresh(context);
        DailyWidgetBridge bridge = DailyWidgetBridge.current();
        if (bridge != null && bridge.isReady()) { bridge.dispatch(command); return; }
        String commandId = command.get("commandId").getAsString();
        if (!IN_FLIGHT.add(commandId)) return;
        PendingResult pending = goAsync();
        Context app = context.getApplicationContext();
        new Thread(() -> {
            try {
                DailyWidgetHeadlessExecutor.Outcome result = DailyWidgetHeadlessExecutor.run(app, command);
                new DailyWidgetStore(app).ack(commandId, result.status);
                DailyWidgetProvider.refresh(app);
                if (!"applied".equals(result.status)) new Handler(Looper.getMainLooper()).post(() ->
                        Toast.makeText(app, result.message, Toast.LENGTH_SHORT).show());
            } catch (RuntimeException error) {
                new DailyWidgetStore(app).ack(commandId, "failed");
                new Handler(Looper.getMainLooper()).post(() -> Toast.makeText(app,
                        "操作未确认，点击可重试", Toast.LENGTH_SHORT).show());
            } finally { IN_FLIGHT.remove(commandId); pending.finish(); }
        }, "DailyWidgetCommand").start();
    }
    static void retryPendingIgnore(Context context) {
        Context app = context.getApplicationContext();
        DailyWidgetStore store = new DailyWidgetStore(app);
        JsonObject command = store.pendingIgnore();
        if (command == null) return;
        String commandId = command.get("commandId").getAsString();
        if (!IN_FLIGHT.add(commandId)) return;
        new Thread(() -> {
            try {
                WidgetTimerRuntimeStore.Config runtime = new WidgetTimerRuntimeStore(app).read();
                String result = runtime != null && runtime.verifiedUserId.equals(command.get("userId").getAsString())
                        && runtime.generation == command.get("generation").getAsLong()
                        ? new DailyWidgetHabitClient().ignore(runtime, command) : "retryable";
                if ("applied".equals(result) || "rejected".equals(result)) {
                    store.ackIgnore(commandId, "applied".equals(result));
                    DailyWidgetProvider.refresh(app);
                }
                if ("rejected".equals(result)) new Handler(Looper.getMainLooper()).post(() ->
                        Toast.makeText(app, "忽略今天未被接受，请刷新", Toast.LENGTH_SHORT).show());
            } finally { IN_FLIGHT.remove(commandId); }
        }, "DailyWidgetIgnore").start();
    }
    private static void openChecklist(Context context) {
        context.startActivity(new Intent(context, MainActivity.class)
                .putExtra("route", "checklist")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
}
