package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.Test;

public class TimerWidgetRefreshLayoutTest {
    @Test public void syncControlFollowsStopAndRendererKeepsExistingActions() throws Exception {
        String layout = new String(Files.readAllBytes(Paths.get("src","main","res","layout","timer_widget.xml")), StandardCharsets.UTF_8);
        assertTrue(layout.indexOf("@+id/widget_stop") < layout.indexOf("@+id/widget_sync"));
        assertTrue(layout.contains("android:layout_width=\"44dp\"") && layout.contains("android:contentDescription=\"同步最新计时状态\""));
        String renderer = new String(Files.readAllBytes(Paths.get("src","main","java","com","mytimelogger","app","TimerWidgetRenderer.java")), StandardCharsets.UTF_8);
        assertTrue(renderer.contains("setOnClickPendingIntent(R.id.widget_sync"));
        assertTrue(renderer.contains("WidgetTimerCommandReceiver.refreshPendingIntent(context)"));
        assertTrue(renderer.contains("setOnClickPendingIntent(R.id.widget_stop"));
        assertTrue(renderer.contains("setPendingIntentTemplate(R.id.widget_grid"));
    }

    @Test public void refreshPathIsReadOnlyAndDoesNotUseCommandJournal() throws Exception {
        String receiver = new String(Files.readAllBytes(Paths.get("src","main","java","com","mytimelogger","app","WidgetTimerCommandReceiver.java")), StandardCharsets.UTF_8);
        int start = receiver.indexOf("private static void refreshRuntime");
        int end = receiver.indexOf("private static String applyRuntime", start);
        String refresh = receiver.substring(start, end);
        assertTrue(refresh.contains("readCurrentState(runtime)"));
        for(String forbidden:new String[]{".execute(","WidgetCommandStore","WidgetIntegrationJournal","startPendingIntent","stopPendingIntent"}) assertFalse(forbidden,refresh.contains(forbidden));
    }
}
