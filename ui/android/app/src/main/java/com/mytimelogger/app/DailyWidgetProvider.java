package com.mytimelogger.app;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.widget.RemoteViews;

public final class DailyWidgetProvider extends AppWidgetProvider {
    @Override public void onEnabled(Context context) { refresh(context); }
    @Override public void onUpdate(Context context, AppWidgetManager manager, int[] ids) { refresh(context); }
    @Override public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (intent != null && intent.getAction() != null &&
                (Intent.ACTION_DATE_CHANGED.equals(intent.getAction())
                || Intent.ACTION_TIMEZONE_CHANGED.equals(intent.getAction())
                || Intent.ACTION_TIME_CHANGED.equals(intent.getAction()))) refresh(context);
    }
    static void refresh(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        int[] ids = manager.getAppWidgetIds(new ComponentName(context, DailyWidgetProvider.class));
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.daily_widget);
            Intent service = new Intent(context, DailyWidgetViewsService.class)
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id)
                    .setData(Uri.parse("mtl://daily-widget/" + id));
            views.setRemoteAdapter(R.id.daily_list, service);
            views.setPendingIntentTemplate(R.id.daily_list, PendingIntent.getBroadcast(context, id,
                    new Intent(DailyWidgetCommandReceiver.ACTION).setPackage(context.getPackageName())
                            .setClass(context, DailyWidgetCommandReceiver.class),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE));
            PendingIntent open = PendingIntent.getActivity(context, 0x444100 + id,
                    new Intent(context, MainActivity.class).putExtra("route", "checklist")
                            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            views.setOnClickPendingIntent(R.id.daily_title, open);
            views.setOnClickPendingIntent(R.id.daily_refresh, open);
            manager.updateAppWidget(id, views);
            manager.notifyAppWidgetViewDataChanged(id, R.id.daily_list);
        }
    }
}
