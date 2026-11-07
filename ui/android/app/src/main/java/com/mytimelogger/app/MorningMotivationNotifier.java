package com.mytimelogger.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import androidx.core.app.NotificationManagerCompat;

final class MorningMotivationNotifier {
    static boolean notifyAt(Context context, long now, boolean trial) {
        var prefs = context.getSharedPreferences("morning_motivation_v1", Context.MODE_PRIVATE);
        if (!trial && !prefs.getBoolean("enabled", true)) return false;
        String account = MorningMotivationStore.account(context), date = DailyWidgetStore.dayAt(now);
        if (account == null || (!trial && (account + ":" + date).equals(prefs.getString("last_notified", "")))) return false;
        String message = MorningMotivationStore.today(context, date);
        NotificationManagerCompat manager = NotificationManagerCompat.from(context);
        if (message == null || !manager.areNotificationsEnabled()) { prefs.edit().putString("last_result", "permission_denied").apply(); return false; }
        if (Build.VERSION.SDK_INT >= 26) context.getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel("morning_motivation", "早间激励", NotificationManager.IMPORTANCE_HIGH));
        PendingIntent open = PendingIntent.getActivity(context, 870, new Intent(context, MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(context, "morning_motivation") : new Notification.Builder(context);
        manager.notify(trial ? 871 : 870, builder.setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(trial ? "早间激励试发" : "早安，今天也一起向前")
            .setContentText(message).setContentIntent(open).setAutoCancel(true).build());
        String at = java.time.Instant.ofEpochMilli(now).atZone(java.time.ZoneId.of("Asia/Shanghai"))
            .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"));
        var edit = prefs.edit().putString("last_result", trial ? "trial_delivered" : "delivered").putString("last_at", at);
        if (!trial) edit.putString("last_notified", account + ":" + date);
        edit.apply();
        return true;
    }
    private MorningMotivationNotifier() {}
}
