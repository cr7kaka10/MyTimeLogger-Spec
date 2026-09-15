package com.mytimelogger.app;

import static org.junit.Assert.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.Test;

public class TimerWidgetAiEntryContractTest {
    @Test public void flashEntryUsesCategorySizeAndOnlyRoutesToTheExistingPrompt() throws Exception {
        String layout = read("src/main/res/layout/timer_widget.xml");
        String item = read("src/main/res/layout/timer_widget_category_item.xml");
        String provider = read("src/main/java/com/mytimelogger/app/TimerWidgetProvider.java");
        String renderer = read("src/main/java/com/mytimelogger/app/TimerWidgetRenderer.java");
        String factory = read("src/main/java/com/mytimelogger/app/TimerWidgetViewsFactory.java");
        String receiver = read("src/main/java/com/mytimelogger/app/WidgetTimerCommandReceiver.java");
        String activity = read("src/main/java/com/mytimelogger/app/MainActivity.java");
        String app = read("../../src/App.tsx");
        assertTrue(item.contains("@+id/widget_category_flash"));
        assertTrue(item.contains("@+id/widget_category_flash_label"));
        assertTrue(item.contains("<ImageView\n        android:id=\"@+id/widget_category_flash\""));
        assertTrue(item.contains("android:src=\"@drawable/timer_widget_flash\""));
        assertTrue(!item.contains("android:text=\"闪\""));
        assertTrue(item.contains("android:text=\"闪念\""));
        assertTrue(item.contains("android:contentDescription=\"记录闪念\""));
        assertTrue(item.contains("android:layout_height=\"60dp\""));
        assertTrue(layout.contains("@+id/widget_grid_divider"));
        assertTrue(layout.contains("@drawable/timer_widget_category_divider"));
        assertTrue(layout.contains("android:verticalSpacing=\"@dimen/timer_widget_grid_row_spacing\""));
        assertTrue(layout.contains("android:paddingTop=\"@dimen/timer_widget_grid_edge_padding\""));
        assertTrue(layout.contains("android:paddingBottom=\"@dimen/timer_widget_grid_edge_padding\""));
        assertTrue(!layout.contains("输入 AI 管理需求"));
        assertTrue(layout.indexOf("@+id/widget_header") < layout.indexOf("@+id/widget_grid"));
        assertTrue(!layout.contains("@+id/widget_ai_entry"));
        assertTrue(provider.contains("ACTION_OPEN_AI_PROMPT"));
        assertTrue(provider.contains("focus_ai_prompt"));
        assertTrue(factory.contains("FLASH_AFTER_CATEGORY_COUNT = 15"));
        assertTrue(factory.contains("setImageViewResource(R.id.widget_category_flash, R.drawable.timer_widget_flash)"));
        assertTrue(!factory.contains("setTextColor(R.id.widget_category_flash,"));
        assertTrue(factory.contains("setViewVisibility(R.id.widget_category_flash_label"));
        assertTrue(factory.contains("WidgetTimerCommandReceiver.ACTION_OPEN_AI_PROMPT"));
        assertTrue(receiver.contains("TimerWidgetProvider.openTimerAiIntent(context)"));
        assertTrue(!renderer.contains("当前未计时"));
        assertTrue(!renderer.contains("选择下方分类开始计时"));
        assertTrue(activity.contains("focusAi"));
        assertTrue(activity.contains("__mtlPendingNavigation"));
        assertTrue(app.contains("__mtlPendingNavigation"));
        assertTrue(Files.size(Paths.get("src/main/res/drawable-nodpi/timer_widget_flash.png")) > 0);
    }

    private static String read(String path) throws Exception {
        return new String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8);
    }
}
