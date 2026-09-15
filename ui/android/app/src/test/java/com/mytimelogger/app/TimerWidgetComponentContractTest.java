package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
import org.junit.Test;

public class TimerWidgetComponentContractTest {
    @Test public void manifestRegistersOnlyScopedWidgetComponents() throws Exception {
        String manifest = read("src", "main", "AndroidManifest.xml");
        for (String token : Arrays.asList(
                ".TimerWidgetProvider", "android.appwidget.action.APPWIDGET_UPDATE",
                "@xml/timer_widget_info", ".TimerWidgetViewsService",
                "android.permission.BIND_REMOTEVIEWS", ".WidgetTimerCommandReceiver",
                ".TimerWidgetBootReceiver", "android.intent.action.BOOT_COMPLETED",
                "android.permission.RECEIVE_BOOT_COMPLETED"))
            assertTrue(token, manifest.contains(token));
        assertFalse(manifest.contains("SCHEDULE_EXACT_ALARM"));
        assertFalse(manifest.contains("AlarmReceiver"));
    }

    @Test public void gradleUsesCoreAndroidxWithoutCompose() throws Exception {
        String gradle = read("build.gradle");
        assertTrue(gradle.contains("androidx.core:core:$androidxCoreVersion"));
        assertFalse(gradle.toLowerCase().contains("compose"));
    }

    @Test public void widgetLayoutsKeepTheHeaderBlankAndCategoriesTransparent() throws Exception {
        String widget = read("src", "main", "res", "layout", "timer_widget.xml");
        String item = read("src", "main", "res", "layout", "timer_widget_category_item.xml");
        for (String token : Arrays.asList("<LinearLayout", "@+id/widget_header", "@+id/widget_grid",
                "@color/timer_widget_text_secondary", "@+id/widget_stop", "@+id/widget_grid_divider",
                "@drawable/timer_widget_category_divider",
                "android:verticalSpacing=\"@dimen/timer_widget_grid_row_spacing\"",
                "<FrameLayout", "@+id/widget_grid_frame"))
            assertTrue(token, widget.contains(token));
        assertTrue(widget.contains("@drawable/timer_widget_stop_button"));
        assertTrue(widget.contains("<TextView\n        android:id=\"@+id/widget_grid_divider\""));
        assertFalse(widget.contains("<View"));
        for (String token : Arrays.asList("选择分类", "记录闪念", "闪念", "@+id/widget_category_flash_label",
                "android:minHeight=\"48dp\"", "@color/timer_widget_text_primary"))
            assertTrue(token, item.contains(token));
        assertFalse(item.contains("timer_widget_category_divider"));
        assertFalse(item.contains("widget_category_state"));
        assertFalse(item.contains("android:text=\"仅App操作\""));

        String debugNetwork = read("src", "debug", "res", "xml", "network_security_config.xml");
        assertTrue(debugNetwork.contains("<base-config cleartextTrafficPermitted=\"true\""));
        assertFalse(debugNetwork.contains("192.168.1.80"));
        assertFalse(Files.exists(Paths.get("src", "main", "res", "xml", "network_security_config.xml")));
    }

    @Test public void widgetIsFixedFiveByFourAndAlwaysDarkTranslucent() throws Exception {
        String info = read("src", "main", "res", "xml", "timer_widget_info.xml");
        assertTrue(info.contains("android:targetCellWidth=\"5\""));
        assertTrue(info.contains("android:targetCellHeight=\"4\""));
        assertTrue(info.contains("android:minHeight=\"200dp\""));
        assertTrue(info.contains("android:resizeMode=\"horizontal|vertical\""));
        assertFalse(info.contains("minResize"));

        String widget = read("src", "main", "res", "layout", "timer_widget.xml");
        String item = read("src", "main", "res", "layout", "timer_widget_category_item.xml");
        assertTrue(widget.contains("android:numColumns=\"5\""));
        assertTrue(widget.contains("android:layout_height=\"44dp\""));
        assertTrue(widget.indexOf("@+id/widget_header") < widget.indexOf("@+id/widget_grid"));
        assertFalse(widget.contains("@+id/widget_ai_entry"));
        assertTrue(widget.contains("android:layout_height=\"0dp\"\n        android:layout_weight=\"1\""));
        assertTrue(widget.contains("android:layout_height=\"match_parent\"\n            android:gravity=\"top\""));
        assertFalse(widget.contains("android:layout_height=\"176dp\""));
        assertFalse(widget.contains("android:layout_gravity=\"center_vertical\""));
        assertTrue(item.contains("android:layout_height=\"60dp\""));

        String values = read("src", "main", "res", "values", "timer_widget_values.xml");
        assertTrue(values.contains("name=\"timer_widget_grid_row_spacing\">0dp"));
        assertTrue(values.contains("name=\"timer_widget_grid_edge_padding\">0dp"));
        assertTrue(values.contains("name=\"timer_widget_padding\">8dp"));

        String day = read("src", "main", "res", "values", "timer_widget_values.xml");
        String night = read("src", "main", "res", "values-night", "timer_widget_values.xml");
        for (String token : Arrays.asList("#CC111317", "#F2FFFFFF", "#B3EBEBF5", "#38FFFFFF")) {
            assertTrue("day " + token, day.contains(token));
            assertTrue("night " + token, night.contains(token));
        }
    }

    @Test public void headerOpensTimerWhileChildrenOwnSingleActions() throws Exception {
        String renderer = read("src", "main", "java", "com", "mytimelogger", "app", "TimerWidgetRenderer.java");
        String provider = read("src", "main", "java", "com", "mytimelogger", "app", "TimerWidgetProvider.java");
        String activity = read("src", "main", "java", "com", "mytimelogger", "app", "MainActivity.java");
        String app = read("..", "..", "src", "App.tsx");
        assertEquals(1, count(renderer, "setOnClickPendingIntent(R.id.widget_root, null)"));
        assertEquals(1, count(renderer, "setOnClickPendingIntent(R.id.widget_header"));
        assertEquals(1, count(renderer, "setPendingIntentTemplate(R.id.widget_grid"));
        assertEquals(0, count(renderer, "setOnClickPendingIntent(R.id.widget_ai_entry"));
        assertEquals(1, count(renderer, "setOnClickPendingIntent(R.id.widget_stop"));
        for (String token : Arrays.asList("MainActivity.class", "PendingIntent.getActivity",
                "putExtra(\"route\", \"timer\")", "PendingIntent.FLAG_IMMUTABLE"))
            assertTrue(token, provider.contains(token));
        assertTrue(activity.contains("onNewIntent(Intent intent)"));
        assertTrue(activity.contains("mtl:navigate"));
        assertTrue(app.contains("addEventListener('mtl:navigate'"));
    }

    private static int count(String value, String token) {
        int total = 0, offset = 0;
        while ((offset = value.indexOf(token, offset)) >= 0) { total++; offset += token.length(); }
        return total;
    }

    private static String read(String... path) throws Exception {
        return new String(Files.readAllBytes(Paths.get("", path)), StandardCharsets.UTF_8);
    }
}
