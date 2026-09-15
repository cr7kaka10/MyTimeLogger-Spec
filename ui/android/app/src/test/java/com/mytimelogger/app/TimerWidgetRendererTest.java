package com.mytimelogger.app;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.Test;

import static org.junit.Assert.*;

public class TimerWidgetRendererTest {
    @Test
    public void headerIsHiddenWhileIdleAndRetainsTheRunningTimerControls() throws Exception {
        String layout = read("src/main/res/layout/timer_widget.xml");
        String renderer = read("src/main/java/com/mytimelogger/app/TimerWidgetRenderer.java");
        assertTrue(layout.contains("<LinearLayout"));
        assertTrue(layout.contains("android:id=\"@+id/widget_header\""));
        for (String retainedId : new String[] {
                "widget_icon", "widget_title", "widget_status", "widget_chronometer", "widget_note", "widget_stop" }) {
            assertTrue(layout.contains(retainedId));
            assertTrue(renderer.contains("R.id." + retainedId));
        }
        assertTrue(renderer.contains("header.statusBandVisible ? View.VISIBLE : View.INVISIBLE"));
        assertFalse(renderer.contains("当前未计时"));
        assertFalse(renderer.contains("选择下方分类开始计时"));
    }

    @Test
    public void categoryVisualKeepsOriginalShapeAndDisablesInputOutput() {
        WidgetTimerRepository.Category sport = new WidgetTimerRepository.Category(
                2L, "运动", "atm:sp_068", "#12AB34");
        TimerWidgetRenderer.CategoryVisual ordinary = TimerWidgetRenderer.category(sport, "只显示", 0xFF888888);
        assertEquals(R.drawable.ic_timer_category_fallback, ordinary.iconRes);
        assertEquals("public/icons/atm/sp_068.png", ordinary.assetPath);
        assertTrue(ordinary.tintable);
        assertEquals(0xFF12AB34, ordinary.tint);
        assertEquals("运动", ordinary.name);
        assertEquals("只显示", ordinary.note);
        assertTrue(ordinary.attachPendingIntent);

        WidgetTimerRepository.Category input = new WidgetTimerRepository.Category(
                3L, "输入", "atm:cat_96", "#123456");
        TimerWidgetRenderer.CategoryVisual disabled = TimerWidgetRenderer.category(input, null, 0xFF888888);
        assertEquals(R.drawable.ic_timer_category_fallback, disabled.iconRes);
        assertEquals(0xFF888888, disabled.tint);
        assertEquals("", disabled.note);
        assertFalse(disabled.enabled);
        assertFalse(disabled.attachPendingIntent);
    }

    @Test
    public void persistedSnapshotParsesHeaderFieldsAndDisplayOnlyNote() {
        String json = "{\"version\":1,\"capturedAtEpochMs\":15000,\"state\":\"countup_studying\"," +
                "\"isPaused\":false,\"category\":{\"id\":2,\"name\":\"运动\",\"task\":\"桌面备注\"}," +
                "\"session\":{\"startedAtEpochMs\":10000},\"timing\":{\"elapsedMs\":3000}}";
        WidgetTimerSnapshotParser.Parsed parsed = WidgetTimerSnapshotParser.parse(json);
        assertNotNull(parsed);
        assertEquals("countup_studying", parsed.snapshot.state);
        assertEquals(Long.valueOf(2L), parsed.snapshot.categoryId);
        assertEquals("运动", parsed.snapshot.categoryName);
        assertEquals(3_000L, parsed.snapshot.elapsedMs);
        assertEquals(Long.valueOf(10_000L), parsed.snapshot.startedAtEpochMs);
        assertEquals("桌面备注", parsed.note);
        assertNull(WidgetTimerSnapshotParser.parse("{\"version\":2}"));
    }

    private static String read(String path) throws Exception {
        return new String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8);
    }
}
