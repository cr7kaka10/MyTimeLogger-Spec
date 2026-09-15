package com.mytimelogger.app;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;

public final class TimerWidgetProvider extends AppWidgetProvider {
    public static final String ACTION_COMMAND_APPLIED = "com.mytimelogger.app.WIDGET_COMMAND_APPLIED";
    public static final String ACTION_OPEN_AI_PROMPT = "com.mytimelogger.app.OPEN_AI_PROMPT";
    private static long lastRenderedRevision = Long.MIN_VALUE;

    static PendingIntent openTimerPendingIntent(Context context) {
        Intent intent = new Intent(context, MainActivity.class)
                .setAction(Intent.ACTION_VIEW).putExtra("route", "timer")
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(context, 0x4d544c,
                intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static PendingIntent openTimerAiPendingIntent(Context context) {
        return PendingIntent.getActivity(context, 0x4d544d,
                openTimerAiIntent(context), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static Intent openTimerAiIntent(Context context) {
        return new Intent(context, MainActivity.class)
                .setAction(ACTION_OPEN_AI_PROMPT).putExtra("route", "timer").putExtra("focus_ai_prompt", true)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    }

    @Override public void onEnabled(Context context) { refresh(context, "enable"); }
    @Override public void onUpdate(Context context, AppWidgetManager manager, int[] ids) { refresh(context, "update"); }
    @Override public void onAppWidgetOptionsChanged(Context context, AppWidgetManager manager, int id, Bundle options) { refresh(context, "options"); }
    @Override public void onDeleted(Context context, int[] ids) { /* timer snapshot remains authoritative */ }

    @Override public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        String action = intent == null ? null : intent.getAction();
        if (Intent.ACTION_CONFIGURATION_CHANGED.equals(action)) refresh(context, "theme");
        if (ACTION_COMMAND_APPLIED.equals(action)) refresh(context, "command");
    }

    private static void refresh(Context context, String reason) {
        TimerWidgetRenderer.refreshAll(context, reason);
    }
    private static long currentRevision(Context context) {
        if (context == null) return Long.MIN_VALUE;
        WidgetTimerSnapshotParser.Parsed parsed = WidgetTimerSnapshotParser.parse(
                new WidgetTimerPreferences(context).loadSnapshot());
        return parsed == null ? Long.MIN_VALUE : parsed.snapshot.capturedAtEpochMs;
    }
    private static synchronized boolean acceptRevision(long revision) {
        if (!WidgetTimerRepository.acceptsRevision(lastRenderedRevision, revision)) return false;
        lastRenderedRevision = revision; return true;
    }
    static void refreshForTest(String reason) { refresh(null, reason); }
    static boolean refreshRevisionForTest(String reason, long revision) {
        if (!acceptRevision(revision)) return false;
        TimerWidgetRenderer.refreshAll(null, reason); return true;
    }
    static synchronized void resetRevisionForTest() { lastRenderedRevision = Long.MIN_VALUE; }
    static void deleteForTest() { /* intentionally no Preferences/SQLite mutation */ }
}
