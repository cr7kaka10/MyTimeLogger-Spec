package com.mytimelogger.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import com.google.gson.JsonObject;

public final class DailyWidgetCommandReceiver extends BroadcastReceiver {
    static final String ACTION = "com.mytimelogger.app.DAILY_WIDGET_COMMAND";
    @Override public void onReceive(Context context, Intent intent) {
        if (intent == null || !ACTION.equals(intent.getAction())
                || !context.getPackageName().equals(intent.getPackage())
                || intent.getComponent() == null
                || !getClass().getName().equals(intent.getComponent().getClassName())) return;
        String action = intent.getStringExtra("action");
        if ("open".equals(action)) { openChecklist(context); return; }
        if (!"complete".equals(action)) return;
        String kind = intent.getStringExtra("kind"), id = intent.getStringExtra("id");
        String day = intent.getStringExtra("date");
        if (kind == null || id == null || day == null || !day.equals(DailyWidgetStore.today())) return;
        boolean eligible = false;
        for (DailyWidgetRepository.Row row : new DailyWidgetRepository(context).load())
            if (!row.header && !row.checked && row.kind.equals(kind) && row.id.equals(id) && row.day.equals(day)) {
                eligible = true; break;
            }
        if (!eligible) return;
        JsonObject command = new DailyWidgetStore(context).claim(kind, id, day);
        if (command == null) return;
        DailyWidgetBridge bridge = DailyWidgetBridge.current();
        if (bridge != null && bridge.isReady()) bridge.dispatch(command);
        else openChecklist(context);
    }
    private static void openChecklist(Context context) {
        context.startActivity(new Intent(context, MainActivity.class)
                .putExtra("route", "checklist")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
}
