package com.mytimelogger.app;

import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.SystemClock;
import android.view.View;
import android.widget.RemoteViews;
import java.util.List;

public final class TimerWidgetRenderer {
    static final class Header {
        final String mode;
        final long elapsedMs;
        final long chronometerBase;
        final boolean chronometerRunning;
        final boolean stopVisible;
        final boolean readonly;
        final boolean statusBandVisible;
        final String title;

        Header(String mode, long elapsedMs, long chronometerBase,
               boolean chronometerRunning, boolean stopVisible, boolean readonly, String title) {
            this.mode = mode;
            this.elapsedMs = elapsedMs;
            this.chronometerBase = chronometerBase;
            this.chronometerRunning = chronometerRunning;
            this.stopVisible = stopVisible;
            this.readonly = readonly;
            this.statusBandVisible = true;
            this.title = "stopped".equals(mode) ? "" : title;
        }
    }

    static final class CategoryVisual {
        final int iconRes;
        final int tint;
        final String assetPath;
        final boolean tintable;
        final String name;
        final String note;
        final boolean enabled;
        final boolean attachPendingIntent;

        CategoryVisual(int iconRes, int tint, String assetPath, boolean tintable,
                       String name, String note, boolean enabled) {
            this.iconRes = iconRes; this.tint = tint; this.assetPath = assetPath;
            this.tintable = tintable; this.name = name; this.note = note;
            this.enabled = enabled; this.attachPendingIntent = enabled;
        }
    }

    interface RefreshSink { void refresh(Context context, String reason); }
    private static volatile RefreshSink sink;

    private TimerWidgetRenderer() {}

    public static void refreshAll(Context context, String reason) {
        Context app = context == null ? null : context.getApplicationContext();
        if (sink != null) sink.refresh(app, reason);
        else if (app != null) render(app);
    }

    private static void render(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        int[] ids = manager.getAppWidgetIds(new ComponentName(context, TimerWidgetProvider.class));
        long now = System.currentTimeMillis();
        WidgetTimerSnapshotParser.Parsed parsed = WidgetTimerSnapshotParser.parse(
                new WidgetTimerPreferences(context).loadSnapshot());
        WidgetTimerEngine.Snapshot snapshot = parsed == null ? WidgetTimerEngine.Snapshot.stopped(now) : parsed.snapshot;
        Header header = header(snapshot, now, SystemClock.elapsedRealtime());
        List<WidgetTimerRepository.Category> categories = new WidgetTimerRepository(context).loadCategories();
        WidgetTimerRepository.Category active = null;
        for (WidgetTimerRepository.Category item : categories)
            if (snapshot.categoryId != null && item.id == snapshot.categoryId) { active = item; break; }
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.timer_widget);
            views.setInt(R.id.widget_root, "setBackgroundResource", R.drawable.timer_widget_background);
            // Remove the pre-upgrade whole-card action retained by Launcher before assigning child actions.
            views.setOnClickPendingIntent(R.id.widget_root, null);
            views.setOnClickPendingIntent(R.id.widget_header,
                    TimerWidgetProvider.openTimerPendingIntent(context));
            views.setViewVisibility(R.id.widget_header, header.statusBandVisible ? View.VISIBLE : View.INVISIBLE);
            views.setTextViewText(R.id.widget_title, header.title);
            String status = statusText(header);
            views.setViewVisibility(R.id.widget_title, header.title.isEmpty() ? View.GONE : View.VISIBLE);
            views.setTextViewText(R.id.widget_status, status);
            views.setViewVisibility(R.id.widget_status, status.isEmpty() ? View.GONE : View.VISIBLE);
            views.setChronometer(R.id.widget_chronometer, header.chronometerBase, null, header.chronometerRunning);
            views.setViewVisibility(R.id.widget_chronometer, "stopped".equals(header.mode) ? View.GONE : View.VISIBLE);
            views.setViewVisibility(R.id.widget_stop, header.stopVisible ? View.VISIBLE : View.GONE);
            views.setOnClickPendingIntent(R.id.widget_sync,
                    WidgetTimerCommandReceiver.refreshPendingIntent(context));
            String note = parsed == null ? "" : parsed.note;
            views.setTextViewText(R.id.widget_note, note);
            views.setViewVisibility(R.id.widget_note, note.isEmpty() || "stopped".equals(header.mode) ? View.GONE : View.VISIBLE);
            views.setViewVisibility(R.id.widget_icon, active == null ? View.INVISIBLE : View.VISIBLE);
            if (active != null) {
                CategoryVisual visual = category(active, note, context.getColor(R.color.timer_widget_disabled));
                Bitmap bitmap = CategoryIconResourceMap.bitmapFor(context, active.icon);
                if (bitmap == null) views.setImageViewResource(R.id.widget_icon, visual.iconRes);
                else views.setImageViewBitmap(R.id.widget_icon, bitmap);
                if (visual.tintable) views.setInt(R.id.widget_icon, "setColorFilter", visual.tint);
            }
            Intent service = new Intent(context, TimerWidgetViewsService.class)
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id).setData(Uri.parse("mtl://widget/" + id));
            views.setRemoteAdapter(R.id.widget_grid, service);
            views.setPendingIntentTemplate(R.id.widget_grid,
                    WidgetTimerCommandReceiver.collectionTemplate(context, id));
            if (header.stopVisible && snapshot.categoryId != null)
                views.setOnClickPendingIntent(R.id.widget_stop,
                        WidgetTimerCommandReceiver.stopPendingIntent(context, snapshot.categoryId));
            views.setViewVisibility(R.id.widget_empty, categories.isEmpty() ? View.VISIBLE : View.GONE);
            manager.updateAppWidget(id, views);
            manager.notifyAppWidgetViewDataChanged(id, R.id.widget_grid);
        }
    }

    static Header header(WidgetTimerEngine.Snapshot snapshot, long nowEpochMs, long nowElapsedRealtimeMs) {
        boolean stopped = "stopped".equals(snapshot.state);
        boolean ordinary = "countup_studying".equals(snapshot.state)
                && !WidgetTimerCommand.isBlockedCategoryName(snapshot.categoryName);
        boolean readonly = !stopped && !ordinary;
        long elapsed = ordinary
                ? TimerWidgetBootReceiver.recoveredElapsed(snapshot, nowEpochMs)
                : snapshot.elapsedMs;
        boolean running = ordinary && !snapshot.paused;
        String mode = stopped ? "stopped" : readonly ? "readonly" : snapshot.paused ? "paused" : "running";
        return new Header(mode, elapsed, nowElapsedRealtimeMs - elapsed, running, ordinary, readonly,
                snapshot.categoryName);
    }

    static String statusText(Header header) {
        if ("stopped".equals(header.mode)) return "";
        return "paused".equals(header.mode) ? "已暂停" : "";
    }

    static CategoryVisual category(WidgetTimerRepository.Category category, String note, int disabledGrey) {
        boolean enabled = !WidgetTimerCommand.isBlockedCategoryName(category.name);
        return new CategoryVisual(R.drawable.ic_timer_category_fallback,
                CategoryIconResourceMap.tintFor(category.color, !enabled, disabledGrey),
                CategoryIconResourceMap.assetPathFor(category.icon),
                CategoryIconResourceMap.shouldTint(category.icon, !enabled),
                category.name, note == null ? "" : note, enabled);
    }

    static void setRefreshSinkForTest(RefreshSink replacement) {
        sink = replacement;
    }
}
