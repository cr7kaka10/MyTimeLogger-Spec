package com.mytimelogger.app;

import android.app.NotificationManager;
import android.app.AlarmManager;
import android.content.Context;
import android.webkit.JavascriptInterface;
import android.os.Build;
import androidx.core.app.NotificationManagerCompat;
import org.json.JSONArray;
import org.json.JSONObject;
import java.time.LocalDate;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

public final class MorningMotivationBridge {
    static final String JAVASCRIPT_NAME = "MorningMotivationBridge";
    private final Context context;
    MorningMotivationBridge(Context context) { this.context = context.getApplicationContext(); }
    @JavascriptInterface public boolean cacheWeek(String raw) {
        if (MorningMotivationStore.account(context) == null) return false;
        try {
            JSONObject payload = new JSONObject(raw);
            if (!"morning-motivation-v1".equals(payload.getString("version"))) return false;
            JSONArray items = payload.getJSONArray("items");
            if (items.length() != 7) return false;
            String today = DailyWidgetStore.dayAt(System.currentTimeMillis());
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.getJSONObject(i);
                String date = item.getString("date"), message = item.getString("message");
                if (!MorningMotivationStore.valid(date, message) || !LocalDate.parse(today).plusDays(i).toString().equals(date)) return false;
            }
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.getJSONObject(i);
                if (!MorningMotivationStore.put(context, item.getString("date"), item.getString("message"))) return false;
            }
            return true;
        } catch (Exception error) { return false; }
    }
    @JavascriptInterface public void clear() {
        MorningMotivationStore.clear(context, MorningMotivationStore.account(context));
        context.getSharedPreferences("morning_motivation_v1", Context.MODE_PRIVATE).edit().remove("last_notified").apply();
        context.getSystemService(NotificationManager.class).cancel(870);
        context.getSystemService(NotificationManager.class).cancel(871);
    }
    @JavascriptInterface public String status() {
        var prefs = context.getSharedPreferences("morning_motivation_v1", Context.MODE_PRIVATE);
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        boolean exact = alarms != null && (Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms());
        String next = Instant.ofEpochMilli(MorningMotivationReceiver.next(System.currentTimeMillis()))
            .atZone(ZoneId.of("Asia/Shanghai")).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"));
        try { return new JSONObject().put("enabled", prefs.getBoolean("enabled", true))
            .put("permission", NotificationManagerCompat.from(context).areNotificationsEnabled())
            .put("exactAlarm", exact).put("next", next)
            .put("lastResult", prefs.getString("last_result", "未投递"))
            .put("lastAt", prefs.getString("last_at", "")).toString(); }
        catch (Exception error) { return "{}"; }
    }
    @JavascriptInterface public void setEnabled(boolean enabled) {
        context.getSharedPreferences("morning_motivation_v1", Context.MODE_PRIVATE).edit().putBoolean("enabled", enabled).apply();
        MorningMotivationReceiver.schedule(context, System.currentTimeMillis());
        if (!enabled) context.getSystemService(NotificationManager.class).cancel(870);
    }
    @JavascriptInterface public boolean trial() {
        return MorningMotivationNotifier.notifyAt(context, System.currentTimeMillis(), true);
    }
}
