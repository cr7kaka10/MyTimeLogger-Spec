package com.mytimelogger.app;

import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.view.View;
import android.widget.RemoteViews;
import android.widget.RemoteViewsService;
import java.util.Collections;
import java.util.List;

public final class DailyWidgetViewsFactory implements RemoteViewsService.RemoteViewsFactory {
    private final Context context;
    private List<DailyWidgetRepository.Row> rows = Collections.emptyList();
    DailyWidgetViewsFactory(Context context) { this.context = context; }
    @Override public void onCreate() { onDataSetChanged(); }
    @Override public void onDataSetChanged() { rows = new DailyWidgetRepository(context).load(); }
    @Override public void onDestroy() { rows = Collections.emptyList(); }
    @Override public int getCount() { return rows.size(); }
    @Override public RemoteViews getViewAt(int position) {
        if (position < 0 || position >= rows.size()) return null;
        DailyWidgetRepository.Row row = rows.get(position);
        RemoteViews view = new RemoteViews(context.getPackageName(), R.layout.daily_widget_row);
        view.setTextViewText(R.id.daily_name, row.title);
        view.setTextViewText(R.id.daily_badge, row.badge);
        view.setViewVisibility(R.id.daily_check, row.header ? View.GONE : View.VISIBLE);
        view.setTextViewText(R.id.daily_check, row.checked ? "☑" : "□");
        view.setTextColor(R.id.daily_name, row.header ? Color.rgb(188, 181, 211) : Color.WHITE);
        view.setTextColor(R.id.daily_badge, row.header ? Color.rgb(188, 181, 211)
                : row.badge.equals("今天") || row.badge.equals("习惯") ? Color.rgb(116, 151, 255) : Color.rgb(255, 92, 92));
        view.setContentDescription(R.id.daily_row, row.header ? row.title : row.title + "，" + row.badge);
        if (!row.header) {
            Intent open = new Intent().putExtra("action", "open").putExtra("kind", row.kind)
                    .putExtra("id", row.id).putExtra("date", row.day);
            view.setOnClickFillInIntent(R.id.daily_name, open);
            view.setOnClickFillInIntent(R.id.daily_badge, open);
            if (!row.checked) view.setOnClickFillInIntent(R.id.daily_check, new Intent()
                    .putExtra("action", "complete").putExtra("kind", row.kind)
                    .putExtra("id", row.id).putExtra("date", row.day));
        }
        return view;
    }
    @Override public RemoteViews getLoadingView() { return null; }
    @Override public int getViewTypeCount() { return 1; }
    @Override public long getItemId(int position) {
        DailyWidgetRepository.Row row = rows.get(position);
        return (row.header ? "header:" + row.title : row.kind + ":" + row.id).hashCode() & 0xffffffffL;
    }
    @Override public boolean hasStableIds() { return true; }
}
