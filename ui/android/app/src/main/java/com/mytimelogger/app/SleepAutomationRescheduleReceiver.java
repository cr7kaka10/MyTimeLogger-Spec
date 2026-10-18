package com.mytimelogger.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

public final class SleepAutomationRescheduleReceiver extends BroadcastReceiver {
    static final String PREFS = "sleep_automation", ENABLED = "enabled", NEXT = "next_alarm";

    static boolean shouldSchedule(boolean enabled, long saved, long next) {
        return enabled;
    }

    static void setEnabled(Context context, boolean enabled) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(ENABLED, enabled).apply();
    }

    @Override public void onReceive(Context context, Intent ignored) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        long next = SleepAutomationScheduler.next840(System.currentTimeMillis());
        if (!shouldSchedule(prefs.getBoolean(ENABLED, false), prefs.getLong(NEXT, 0), next)) return;
        SleepAutomationAlarmReceiver.scheduleNext(context, System.currentTimeMillis());
    }
}
