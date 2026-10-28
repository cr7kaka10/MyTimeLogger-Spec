package com.mytimelogger.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import androidx.core.app.NotificationManagerCompat;

final class MealDeadlineNotifier {
    static void notifyPending(Context context, long now, int meal) {
        NotificationManagerCompat manager = NotificationManagerCompat.from(context);
        if (!manager.areNotificationsEnabled()) return;
        String account = new WidgetTimerPreferences(context).loadActiveDatabaseName();
        String key = account + ":" + DailyWidgetStore.dayAt(now) + ":" + meal;
        var prefs = context.getSharedPreferences("meal_deadline_v1", Context.MODE_PRIVATE);
        if (key.equals(prefs.getString("last_" + meal, ""))) return;
        if (Build.VERSION.SDK_INT >= 26) context.getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel("meal_deadline", "三餐打卡核对", NotificationManager.IMPORTANCE_HIGH));
        PendingIntent open = PendingIntent.getActivity(context, 860 + meal,
            new Intent(context, MainActivity.class).putExtra("route", "exercise").addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(context, "meal_deadline") : new Notification.Builder(context);
        manager.notify(860 + meal, builder.setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(MealDeadlineSchedule.NAMES[meal] + "打卡待核对")
            .setContentText("本机尚未记录按时打卡，请检查并同步；扣币以服务端确认结果为准")
            .setContentIntent(open).setAutoCancel(true).build());
        prefs.edit().putString("last_" + meal, key).apply();
    }
    private MealDeadlineNotifier() {}
}
