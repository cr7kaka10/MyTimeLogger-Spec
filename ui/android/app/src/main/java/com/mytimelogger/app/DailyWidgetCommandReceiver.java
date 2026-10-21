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
        if (!("complete".equals(action) || "fail".equals(action))) return;
        String kind = intent.getStringExtra("kind"), id = intent.getStringExtra("id");
        String day = intent.getStringExtra("date");
        if (kind == null || id == null || day == null || !day.equals(DailyWidgetStore.today())
                || ("fail".equals(action) && !"habit".equals(kind))) return;
        boolean eligible = false;
        for (DailyWidgetRepository.Row row : new DailyWidgetRepository(context).load())
            if (!row.header && !row.checked && row.kind.equals(kind) && row.id.equals(id) && row.day.equals(day)) {
                eligible = true; break;
            }
        if (!eligible) return;
        JsonObject command = new DailyWidgetStore(context).claim(kind, id, day, action);
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
    private static void openChecklist(Context context) {
        context.startActivity(new Intent(context, MainActivity.class)
                .putExtra("route", "checklist")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
}
