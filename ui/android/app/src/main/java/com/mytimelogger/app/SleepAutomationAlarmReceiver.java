package com.mytimelogger.app;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import androidx.core.content.ContextCompat;

public final class SleepAutomationAlarmReceiver extends BroadcastReceiver {
    static final String ACTION = "com.mytimelogger.SLEEP_AUTOMATION_ALARM";
    static final String RETRY_ACTION = "com.mytimelogger.SLEEP_AUTOMATION_RETRY";
    static final int REQUEST_CODE = 840;

    static PendingIntent pending(Context context) {
        Intent intent = new Intent(context, SleepAutomationAlarmReceiver.class).setAction(ACTION);
        return PendingIntent.getBroadcast(context, REQUEST_CODE, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void scheduleNext(Context context, long nowMs) {
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        long at = SleepAutomationScheduler.next840(nowMs);
        if (Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms())
            alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending(context));
        else alarms.setWindow(AlarmManager.RTC_WAKEUP, at, SleepAutomationScheduler.WINDOW_MS, pending(context));
        context.getSharedPreferences(SleepAutomationRescheduleReceiver.PREFS, Context.MODE_PRIVATE)
                .edit().putLong(SleepAutomationRescheduleReceiver.NEXT, at).apply();
    }

    @Override public void onReceive(Context context, Intent intent) {
        if (!context.getSharedPreferences(SleepAutomationRescheduleReceiver.PREFS, Context.MODE_PRIVATE)
                .getBoolean(SleepAutomationRescheduleReceiver.ENABLED, false)) return;
        if (intent != null && ACTION.equals(intent.getAction())) scheduleNext(context, System.currentTimeMillis());
        String sourceAction=intent==null?ACTION:intent.getAction();
        Intent runner = new Intent(sourceAction).setClassName(context, context.getPackageName() + ".SleepAutomationRunnerService")
                .putExtra(SleepAutomationRunnerService.EXTRA_STAGE, "PENDING");
        ContextCompat.startForegroundService(context, runner);
    }
}
