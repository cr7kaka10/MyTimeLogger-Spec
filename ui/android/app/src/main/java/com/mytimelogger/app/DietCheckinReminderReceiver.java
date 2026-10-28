package com.mytimelogger.app;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;
import androidx.core.app.NotificationManagerCompat;

public final class DietCheckinReminderReceiver extends BroadcastReceiver {
    static final String ACTION = "com.mytimelogger.DIET_CHECKIN_REMINDER";
    private static final int REQUEST = 852;
    static PendingIntent pending(Context context) {
        return PendingIntent.getBroadcast(context, REQUEST,
            new Intent(context, DietCheckinReminderReceiver.class).setAction(ACTION),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    static void schedule(Context context, long now) {
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarms == null) return;
        long at = DietCheckinReminderSchedule.next(now);
        try {
            if (Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms())
                alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending(context));
            else alarms.setWindow(AlarmManager.RTC_WAKEUP, at, 60_000, pending(context));
        } catch (SecurityException error) { Log.w("DietReminder", "schedule_denied", error); }
    }
    @Override public void onReceive(Context context, Intent intent) {
        if (intent == null) return;
        long now = System.currentTimeMillis();
        if (ACTION.equals(intent.getAction())) {
            try { if (DietCheckinReminderStore.needsReminder(context, now)) notifyPending(context, now); }
            catch (RuntimeException error) { Log.w("DietReminder", "notify_failed", error); }
        }
        schedule(context, now);
    }
    private static void notifyPending(Context context, long now) {
        String day = DailyWidgetStore.dayAt(now);
        String account = new WidgetTimerPreferences(context).loadActiveDatabaseName();
        String key = account + ":" + day;
        var preferences = context.getSharedPreferences("diet_reminder_v1", Context.MODE_PRIVATE);
        if (key.equals(preferences.getString("last_notified", ""))) return;
        NotificationManagerCompat manager = NotificationManagerCompat.from(context);
        if (!manager.areNotificationsEnabled()) { Log.w("DietReminder", "notification_denied"); return; }
        if (Build.VERSION.SDK_INT >= 26) context.getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel("diet_checkin", "饮食约束打卡提醒", NotificationManager.IMPORTANCE_HIGH));
        PendingIntent open = PendingIntent.getActivity(context, REQUEST,
            new Intent(context, MainActivity.class).putExtra("route", "exercise")
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(context, "diet_checkin") : new Notification.Builder(context);
        manager.notify(REQUEST, builder.setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("饮食约束打卡提醒")
            .setContentText("请在今天结束前完成三项饮食约束打卡")
            .setContentIntent(open).setAutoCancel(true).build());
        preferences.edit().putString("last_notified", key).apply();
    }
}
