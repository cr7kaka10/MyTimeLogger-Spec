package com.mytimelogger.app;

import android.app.PendingIntent;
import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class TimerWidgetViewsFactoryTest {
    private static Map<String, Object> row(long id, String name) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", id); row.put("name", name); row.put("icon", "atm:test"); row.put("color", "#123456");
        return row;
    }

    @Test public void reloadsAllActiveCategoriesInOrderAndDisablesStructuredCategories() {
        final int[] version = {0};
        WidgetTimerRepository repository = new WidgetTimerRepository((sql, parameters) -> {
            List<Map<String, Object>> rows = new ArrayList<>();
            if (version[0]++ > 0) { rows.add(row(99, "最新")); return rows; }
            rows.add(row(1, "输入")); rows.add(row(2, "输出"));
            for (int i = 3; i <= 19; i++) rows.add(row(i, "分类" + i));
            rows.set(2, row(3, "副业生产")); rows.set(11, row(12, "个人杂事")); rows.set(16, row(17, "状态切换"));
            return rows;
        });
        TimerWidgetViewsFactory factory = new TimerWidgetViewsFactory(null, repository);
        factory.onDataSetChanged();
        assertEquals(5, TimerWidgetViewsFactory.COLUMN_COUNT);
        assertEquals(20, factory.getCount());
        assertEquals(4, factory.getCount() / TimerWidgetViewsFactory.COLUMN_COUNT);
        assertFalse(WidgetTimerRepository.categorySqlForTest().contains("LIMIT"));
        assertFalse(factory.isEnabled(0)); assertFalse(factory.isEnabled(1)); assertTrue(factory.isEnabled(2));
        assertTrue(factory.isEnabled(15)); assertNull(factory.categoryAt(15));
        assertEquals("副业生产", factory.categoryAt(2).name);
        assertEquals("个人杂事", factory.categoryAt(11).name);
        assertEquals("状态切换", factory.categoryAt(17).name);
        assertEquals("分类19", factory.categoryAt(19).name);
        assertTrue(TimerWidgetViewsFactory.isFlashPosition(15, 20));
        assertFalse(TimerWidgetViewsFactory.isFlashPosition(14, 20));
        factory.onDataSetChanged();
        assertEquals(2, factory.getCount()); assertEquals("最新", factory.categoryAt(0).name);
        assertNull(factory.categoryAt(1));
    }

    @Test public void itemAndCollectionTemplatePreserveShapeAndDisabledBoundary() {
        TimerWidgetViewsFactory.ItemSpec sport = TimerWidgetViewsFactory.itemSpec(
                new WidgetTimerRepository.Category(2L, "运动", "atm:sp_068", "#12AB34"), 0xFF888888);
        assertEquals(R.drawable.ic_timer_category_fallback, sport.visual.iconRes);
        assertEquals("public/icons/atm/sp_068.png", sport.visual.assetPath);
        assertTrue(sport.visual.tintable);
        assertEquals(0xFF12AB34, sport.visual.tint);
        assertTrue(sport.fillIn);
        assertEquals("运动，开始或切换计时", sport.contentDescription);
        TimerWidgetViewsFactory.ItemSpec input = TimerWidgetViewsFactory.itemSpec(
                new WidgetTimerRepository.Category(1L, "输入", "atm:cat_96", "#123456"), 0xFF888888);
        assertEquals(0xFF888888, input.visual.tint);
        assertFalse(input.fillIn);
        assertEquals("输入，仅App操作", input.contentDescription);
        assertFalse(input.visual.enabled);

        WidgetTimerCommandReceiver.PendingIntentSpec template =
                WidgetTimerCommandReceiver.collectionTemplateSpec("com.mytimelogger.app", 7);
        assertEquals(PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE, template.flags);
        assertEquals(WidgetTimerCommandReceiver.class.getName(), template.componentClassName);
        assertTrue(template.extras.isEmpty());
    }
}
