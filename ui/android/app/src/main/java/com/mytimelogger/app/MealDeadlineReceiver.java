package com.mytimelogger.app;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

public final class MealDeadlineReceiver extends BroadcastReceiver {
    static final String ACTION = "com.mytimelogger.MEAL_DEADLINE";
    private static final int BASE = 860;
    static void schedule(Context context, long now) {
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarms == null) return;
        for (int meal = 0; meal < MealDeadlineSchedule.RULES.length; meal++) {
            PendingIntent pending = PendingIntent.getBroadcast(context, BASE + meal,
                new Intent(context, MealDeadlineReceiver.class).setAction(ACTION).putExtra("meal", meal),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            long at = MealDeadlineSchedule.next(now, meal);
            try {
                if (Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms()) alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending);
                else alarms.setWindow(AlarmManager.RTC_WAKEUP, at, 60_000, pending);
            } catch (SecurityException error) { android.util.Log.w("MealDeadline", "schedule_denied", error); }
        }
    }
    @Override public void onReceive(Context context, Intent intent) {
        long now = System.currentTimeMillis();
        if (intent != null && ACTION.equals(intent.getAction())) {
            int meal = intent.getIntExtra("meal", -1);
            deliverAt(context, now, meal);
        }
        schedule(context, now);
    }
    static void deliverAt(Context context, long now, int meal) {
        if (meal >= 0 && meal < 3 && MealDeadlineSchedule.isDue(now, meal)
            && MealDeadlineState.pending(context, now, meal)) MealDeadlineNotifier.notifyPending(context, now, meal);
    }
}
