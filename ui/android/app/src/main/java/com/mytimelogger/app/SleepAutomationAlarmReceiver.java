package com.mytimelogger.app;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.app.KeyguardManager;
import android.os.Build;
import androidx.core.content.ContextCompat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public final class SleepAutomationAlarmReceiver extends BroadcastReceiver {
    static final String ACTION = "com.mytimelogger.SLEEP_AUTOMATION_ALARM";
    static final String RETRY_ACTION = "com.mytimelogger.SLEEP_AUTOMATION_RETRY";
    static final String UNLOCK_WINDOW_UNTIL = "unlock_window_until", LAST_TRIGGERED_DATE = "last_triggered_date";
    static final int REQUEST_CODE = 840;

    static PendingIntent pending(Context context) {
        Intent intent = new Intent(context, SleepAutomationAlarmReceiver.class).setAction(ACTION);
        return PendingIntent.getBroadcast(context, REQUEST_CODE, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void scheduleNext(Context context, long nowMs) {
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        long at = SleepAutomationScheduler.nextWindowStart(nowMs);
        if (Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms())
            alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending(context));
        else alarms.setWindow(AlarmManager.RTC_WAKEUP, at, SleepAutomationScheduler.WINDOW_MS, pending(context));
        context.getSharedPreferences(SleepAutomationRescheduleReceiver.PREFS, Context.MODE_PRIVATE)
                .edit().putLong(SleepAutomationRescheduleReceiver.NEXT, at).apply();
    }

    @Override public void onReceive(Context context, Intent intent) {
        android.content.SharedPreferences prefs=context.getSharedPreferences(SleepAutomationRescheduleReceiver.PREFS,Context.MODE_PRIVATE);
        if(!prefs.getBoolean(SleepAutomationRescheduleReceiver.ENABLED,false))return;
        long now=System.currentTimeMillis();String action=intent==null?ACTION:intent.getAction();
        if(ACTION.equals(action)){
            long start=prefs.getLong(SleepAutomationRescheduleReceiver.NEXT,0);scheduleNext(context,now);
            if(!SleepAutomationScheduler.withinUnlockWindow(now,start))return;
            prefs.edit().putLong(UNLOCK_WINDOW_UNTIL,SleepAutomationScheduler.windowEnd(start)).apply();
            SleepAutomationNotificationFactory.showUnlockReminder(context);triggerIfUnlocked(context,prefs,now,start);
        }else if(Intent.ACTION_USER_PRESENT.equals(action)){
            long end=prefs.getLong(UNLOCK_WINDOW_UNTIL,0);triggerIfUnlocked(context,prefs,now,end-SleepAutomationScheduler.WINDOW_MS);
        }
    }
    static boolean shouldTrigger(long now,long start,String lastDate,String today){
        return SleepAutomationScheduler.withinUnlockWindow(now,start)&&!today.equals(lastDate);
    }
    private static void triggerIfUnlocked(Context context,android.content.SharedPreferences prefs,long now,long start){
        if(((KeyguardManager)context.getSystemService(Context.KEYGUARD_SERVICE)).isKeyguardLocked())return;
        String today=new SimpleDateFormat("yyyy-MM-dd",Locale.ROOT){{setTimeZone(SleepAutomationScheduler.BEIJING);}}.format(new Date(now));
        String last=prefs.getString(LAST_TRIGGERED_DATE,"");if(!shouldTrigger(now,start,last,today))return;
        prefs.edit().putString(LAST_TRIGGERED_DATE,today).remove(UNLOCK_WINDOW_UNTIL).apply();
        Intent runner=new Intent(context,SleepAutomationRunnerService.class).setAction(ACTION)
                .putExtra(SleepAutomationRunnerService.EXTRA_STAGE,"PENDING");ContextCompat.startForegroundService(context,runner);
    }
}
