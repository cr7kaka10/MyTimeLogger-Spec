package com.mytimelogger.app;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.widget.RemoteViews;
import android.widget.RemoteViewsService;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class TimerWidgetViewsFactory implements RemoteViewsService.RemoteViewsFactory {
    static final class ItemSpec {
        final TimerWidgetRenderer.CategoryVisual visual;
        final boolean fillIn;
        final String contentDescription;
        ItemSpec(TimerWidgetRenderer.CategoryVisual visual, String description) {
            this.visual = visual; this.fillIn = visual.enabled; this.contentDescription = description;
        }
    }
    public static final int COLUMN_COUNT = 5;
    static final int FLASH_AFTER_CATEGORY_COUNT = 15;
    private static final long FLASH_ITEM_ID = Long.MIN_VALUE;
    private final Context context;
    private final WidgetTimerRepository repository;
    private List<WidgetTimerRepository.Category> categories = Collections.emptyList();
    private String action = "start";

    TimerWidgetViewsFactory(Context context, WidgetTimerRepository repository) {
        this.context = context; this.repository = repository;
    }

    @Override public void onCreate() { onDataSetChanged(); }
    @Override public void onDataSetChanged() {
        List<WidgetTimerRepository.Category> latest = repository.loadCategories();
        categories = new ArrayList<>(latest);
        if (context != null) {
            WidgetTimerSnapshotParser.Parsed parsed = WidgetTimerSnapshotParser.parse(
                    new WidgetTimerPreferences(context).loadSnapshot());
            action = parsed != null && !"stopped".equals(parsed.snapshot.state) ? "switch" : "start";
        }
    }
    @Override public void onDestroy() { categories = Collections.emptyList(); }
    @Override public int getCount() { return categories.size() + 1; }
    @Override public RemoteViews getViewAt(int position) {
        if (position < 0 || position >= getCount()) return null;
        if (isFlashPosition(position, categories.size())) return flashView();
        WidgetTimerRepository.Category category = categories.get(categoryIndex(position));
        ItemSpec spec = itemSpec(category, context.getColor(R.color.timer_widget_disabled));
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.timer_widget_category_item);
        views.setViewVisibility(R.id.widget_category_icon, android.view.View.VISIBLE);
        views.setViewVisibility(R.id.widget_category_name, android.view.View.VISIBLE);
        Bitmap bitmap = CategoryIconResourceMap.bitmapFor(context, category.icon);
        if (bitmap == null) views.setImageViewResource(R.id.widget_category_icon, spec.visual.iconRes);
        else views.setImageViewBitmap(R.id.widget_category_icon, bitmap);
        if (spec.visual.tintable) views.setInt(R.id.widget_category_icon, "setColorFilter", spec.visual.tint);
        views.setViewVisibility(R.id.widget_category_flash, android.view.View.GONE);
        views.setViewVisibility(R.id.widget_category_flash_label, android.view.View.GONE);
        views.setTextViewText(R.id.widget_category_name, spec.visual.name);
        views.setTextColor(R.id.widget_category_name, spec.visual.tint);
        views.setContentDescription(R.id.widget_category_item, spec.contentDescription);
        views.setBoolean(R.id.widget_category_item, "setEnabled", spec.visual.enabled);
        if (spec.fillIn) {
            Intent fillIn = new Intent().putExtra("action", action)
                    .putExtra("commandId", "widget-" + category.id + "-" + Long.toHexString(System.nanoTime()))
                    .putExtra("categoryId", category.id).putExtra("eventEpochMs", System.currentTimeMillis());
            views.setOnClickFillInIntent(R.id.widget_category_item, fillIn);
            views.setOnClickFillInIntent(R.id.widget_category_icon, fillIn);
            views.setOnClickFillInIntent(R.id.widget_category_name, fillIn);
        }
        return views;
    }
    private RemoteViews flashView() {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.timer_widget_category_item);
        views.setViewVisibility(R.id.widget_category_icon, android.view.View.GONE);
        views.setViewVisibility(R.id.widget_category_name, android.view.View.GONE);
        views.setViewVisibility(R.id.widget_category_flash, android.view.View.VISIBLE);
        views.setViewVisibility(R.id.widget_category_flash_label, android.view.View.VISIBLE);
        views.setImageViewResource(R.id.widget_category_flash, R.drawable.timer_widget_flash);
        views.setTextColor(R.id.widget_category_flash_label, context.getColor(R.color.timer_widget_text_primary));
        views.setContentDescription(R.id.widget_category_item, "记录闪念");
        Intent fillIn = new Intent().putExtra("action", WidgetTimerCommandReceiver.ACTION_OPEN_AI_PROMPT)
                .putExtra("commandId", "widget-flash-" + Long.toHexString(System.nanoTime()))
                .putExtra("categoryId", 0L).putExtra("eventEpochMs", System.currentTimeMillis());
        views.setOnClickFillInIntent(R.id.widget_category_item, fillIn);
        views.setOnClickFillInIntent(R.id.widget_category_flash, fillIn);
        return views;
    }
    static boolean isFlashPosition(int position, int categoryCount) {
        return position == Math.min(FLASH_AFTER_CATEGORY_COUNT, categoryCount);
    }
    private int categoryIndex(int position) {
        int flashPosition = Math.min(FLASH_AFTER_CATEGORY_COUNT, categories.size());
        return position < flashPosition ? position : position - 1;
    }
    static ItemSpec itemSpec(WidgetTimerRepository.Category category, int disabledGrey) {
        TimerWidgetRenderer.CategoryVisual visual = TimerWidgetRenderer.category(category, "", disabledGrey);
        return new ItemSpec(visual, visual.name + (visual.enabled ? "，开始或切换计时" : "，仅App操作"));
    }
    boolean isEnabled(int position) {
        return isFlashPosition(position, categories.size())
                || !WidgetTimerCommand.isBlockedCategoryName(categories.get(categoryIndex(position)).name);
    }
    WidgetTimerRepository.Category categoryAt(int position) {
        return isFlashPosition(position, categories.size()) ? null : categories.get(categoryIndex(position));
    }
    @Override public RemoteViews getLoadingView() { return null; }
    @Override public int getViewTypeCount() { return 1; }
    @Override public long getItemId(int position) {
        return isFlashPosition(position, categories.size()) ? FLASH_ITEM_ID : categories.get(categoryIndex(position)).id;
    }
    @Override public boolean hasStableIds() { return true; }
}
