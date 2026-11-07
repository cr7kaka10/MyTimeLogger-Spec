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
        boolean menu = "habit".equals(row.kind) && new DailyWidgetStore(context).isMenuOpen(row.id, row.day);
        boolean item = "checklist_item".equals(row.kind);
        boolean progress = "task".equals(row.kind) && !row.progress.isEmpty();
        view.setTextViewText(R.id.daily_name, row.title);
        view.setTextViewText(R.id.daily_item_name, row.title);
        view.setTextViewText(R.id.daily_item_status, row.checked ? "✓" : "○");
        view.setTextViewText(R.id.daily_progress, "步骤 " + row.progress + (row.expanded ? " ⌃" : " ⌄"));
        view.setTextViewText(R.id.daily_badge, row.badge);
        view.setViewVisibility(R.id.daily_name, item ? View.GONE : View.VISIBLE);
        view.setViewVisibility(R.id.daily_item_name, item ? View.VISIBLE : View.GONE);
        view.setViewVisibility(R.id.daily_item_status, item ? View.VISIBLE : View.GONE);
        view.setViewVisibility(R.id.daily_progress, progress ? View.VISIBLE : View.GONE);
        view.setViewVisibility(R.id.daily_badge, menu || item ? View.GONE : View.VISIBLE);
        view.setViewVisibility(R.id.daily_check, row.header || item || !row.blocked.isEmpty() ? View.GONE : View.VISIBLE);
        view.setViewVisibility(R.id.daily_fail, "habit".equals(row.kind) && !row.timed && !menu && row.blocked.isEmpty() ? View.VISIBLE : View.GONE);
        view.setViewVisibility(R.id.daily_cancel, menu ? View.VISIBLE : View.GONE);
        view.setViewVisibility(R.id.daily_confirm, menu && !row.timed && row.blocked.isEmpty() ? View.VISIBLE : View.GONE);
        view.setViewVisibility(R.id.daily_ignore, menu && !row.timed ? View.VISIBLE : View.GONE);
        view.setTextViewText(R.id.daily_check, row.checked ? "☑" : "□");
        view.setContentDescription(R.id.daily_check, row.title + "，标记完成");
        view.setContentDescription(R.id.daily_fail, row.title + "，更多操作");
        view.setContentDescription(R.id.daily_cancel, row.title + "，取消记失败");
        view.setContentDescription(R.id.daily_confirm, row.title + "，确认记失败");
        view.setContentDescription(R.id.daily_ignore, row.title + "，忽略今天");
        view.setContentDescription(R.id.daily_item_status, row.checked ? "已完成" : "未完成");
        view.setContentDescription(R.id.daily_item_name, "检查项，" + row.title);
        view.setContentDescription(R.id.daily_progress, "检查项 " + row.progress + (row.expanded ? "，收起" : "，展开"));
        view.setTextColor(R.id.daily_item_name, context.getColor(row.checked
                ? R.color.timer_widget_text_secondary : R.color.timer_widget_text_primary));
        view.setTextColor(R.id.daily_name, row.header ? Color.rgb(188, 181, 211) : Color.WHITE);
        view.setTextColor(R.id.daily_badge, row.header ? Color.rgb(188, 181, 211)
                : row.badge.equals("处理中") ? Color.rgb(245, 201, 95)
                : row.badge.equals("今天") || row.badge.equals("习惯") ? Color.rgb(116, 151, 255) : Color.rgb(255, 92, 92));
        view.setContentDescription(R.id.daily_row, item ? row.title + (row.checked ? "，已完成" : "，未完成")
                : row.header ? row.title : row.title + "，" + row.badge + (row.timed ? "，定时习惯不可忽略" : ""));
        if (!row.header) {
            Intent open = new Intent().putExtra("action", "open").putExtra("kind", row.kind)
                    .putExtra("id", row.parentId).putExtra("date", row.day);
            view.setOnClickFillInIntent(item ? R.id.daily_item_name : R.id.daily_name, open);
            if (!item && !"habit".equals(row.kind)) view.setOnClickFillInIntent(R.id.daily_badge, open);
            if (progress) view.setOnClickFillInIntent(R.id.daily_progress, new Intent()
                    .putExtra("action", "toggle_items").putExtra("kind", "task")
                    .putExtra("id", row.id).putExtra("date", row.day));
            if (!item && !row.checked) view.setOnClickFillInIntent(R.id.daily_check, new Intent()
                    .putExtra("action", "complete").putExtra("kind", row.kind)
                    .putExtra("id", row.id).putExtra("date", row.day));
            if ("habit".equals(row.kind)) {
                String[] actions = menu ? new String[]{"menu_cancel", "menu_confirm", "menu_ignore"} : new String[]{"menu_open"};
                int[] targets = menu ? new int[]{R.id.daily_cancel, R.id.daily_confirm, R.id.daily_ignore} : new int[]{R.id.daily_fail};
                for (int i = 0; i < actions.length; i++) view.setOnClickFillInIntent(targets[i], new Intent()
                        .putExtra("action", actions[i]).putExtra("kind", row.kind)
                        .putExtra("id", row.id).putExtra("date", row.day));
            }
        }
        return view;
    }
    @Override public RemoteViews getLoadingView() { return null; }
    @Override public int getViewTypeCount() { return 1; }
    @Override public long getItemId(int position) {
        DailyWidgetRepository.Row row = rows.get(position);
        return (row.header ? "header:" + row.title : row.kind + ":" + row.parentId + ":" + row.id).hashCode() & 0xffffffffL;
    }
    @Override public boolean hasStableIds() { return true; }
}
