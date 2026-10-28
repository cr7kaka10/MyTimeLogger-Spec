package com.mytimelogger.app;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import java.util.Calendar;

public final class MorningMotivationReceiver extends BroadcastReceiver {
    static final String ACTION = "com.mytimelogger.MORNING_MOTIVATION";
    private static final int REQUEST = 870;
    static long next(long now) {
        Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        day.setTimeInMillis(now); day.set(Calendar.HOUR_OF_DAY, 7); day.set(Calendar.MINUTE, 30);
        day.set(Calendar.SECOND, 0); day.set(Calendar.MILLISECOND, 0);
        if (day.getTimeInMillis() <= now) day.add(Calendar.DAY_OF_MONTH, 1);
        return day.getTimeInMillis();
    }
    static boolean due(long now) { return next(now - 15 * 60_000) <= now; }
    static PendingIntent pending(Context context) {
        return PendingIntent.getBroadcast(context, REQUEST, new Intent(context, MorningMotivationReceiver.class).setAction(ACTION),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    static void schedule(Context context, long now) {
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarms == null) return;
        if (!context.getSharedPreferences("morning_motivation_v1", Context.MODE_PRIVATE).getBoolean("enabled", true)) {
            alarms.cancel(pending(context)); return;
        }
        long at = next(now);
        try {
            if (Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms()) alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending(context));
            else alarms.setWindow(AlarmManager.RTC_WAKEUP, at, 60_000, pending(context));
        } catch (SecurityException error) { android.util.Log.w("MorningMotivation", "schedule_denied", error); }
    }
    @Override public void onReceive(Context context, Intent intent) {
        long now = System.currentTimeMillis();
        if (intent != null && ACTION.equals(intent.getAction()) && due(now)) MorningMotivationNotifier.notifyAt(context, now, false);
        schedule(context, now);
    }
}
