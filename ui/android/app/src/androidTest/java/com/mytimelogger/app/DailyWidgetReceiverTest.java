package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.Assume;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class DailyWidgetReceiverTest {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    private final String database = "daily-widget-receiver-test.db";
    private SharedPreferences capacitor, runtime, widget;
    private String oldDatabase, oldRuntime, oldSnapshot, oldPending, oldPendingIgnore, oldDone, oldMenu, oldIgnored;
    private SqliteConnection db;
    @Before public void setup() {
        capacitor = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE);
        runtime = context.getSharedPreferences("mtl_widget_runtime_v1", Context.MODE_PRIVATE);
        widget = context.getSharedPreferences("mtl_daily_widget_v1", Context.MODE_PRIVATE);
        oldDatabase = capacitor.getString(WidgetTimerPreferences.ACTIVE_DB_KEY, null);
        oldRuntime = runtime.getString("runtime", null);
        oldSnapshot = widget.getString("snapshot", null); oldPending = widget.getString("pending", null);
        oldPendingIgnore = widget.getString("pending_ignore", null);
        oldDone = widget.getString("done", null); oldMenu = widget.getString("menu", null);
        oldIgnored = widget.getString("ignored", null);
        widget.edit().remove("snapshot").remove("pending").remove("pending_ignore").remove("done").remove("menu").remove("ignored").commit();
        context.deleteDatabase(database);
        db = new SqliteConnection(context, database); db.open();
        db.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,status INTEGER,deleted_at TEXT,title TEXT,due_date TEXT,priority INTEGER,updated_at TEXT,pushed_at TEXT,raw_json TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE habits(id TEXT,name TEXT,is_active INTEGER,source TEXT,sort_order INTEGER,repeat_rule TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE habit_checkins(habit_id TEXT,status INTEGER,checkin_date TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE habit_day_ignores(habit_id TEXT,date TEXT,is_ignored INTEGER)", Collections.emptyList());
        db.execute("CREATE TABLE habit_windows(habit_id TEXT,effective_from TEXT,start_minute INTEGER,end_minute INTEGER)", Collections.emptyList());
        db.execute("CREATE TABLE rewards(id TEXT,title TEXT,unlock_task_id TEXT,is_active INTEGER)", Collections.emptyList());
        db.execute("CREATE TABLE reward_ledger(id TEXT,amount REAL,source_type TEXT,source_id TEXT,description TEXT,created_at TEXT,updated_at TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE system_config(key TEXT,value TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE sync_outbox(id INTEGER PRIMARY KEY,change_id TEXT,device_id TEXT,table_name TEXT,record_id TEXT,operation TEXT,base_version TEXT,payload_json TEXT,status TEXT,retry_count INTEGER,created_at TEXT,updated_at TEXT,last_error TEXT)", Collections.emptyList());
        db.execute("INSERT INTO system_config VALUES('device_id','device-widget-test')", Collections.emptyList());
        db.execute("INSERT INTO tasks(id,status,title,due_date) VALUES('task-1',0,'任务',?)", Collections.singletonList(DailyWidgetStore.today()));
        db.execute("INSERT INTO habits VALUES('habit-1','习惯',0,'local',1,'FREQ=DAILY')", Collections.emptyList());
        db.close();
        JsonObject config = new JsonObject();
        config.addProperty("serverUrl", "http://127.0.0.1:9"); config.addProperty("authToken", "test");
        config.addProperty("deviceId", "device-widget-test"); config.addProperty("verifiedUserId", "widget-test");
        config.addProperty("generation", 777);
        assertTrue(new WidgetTimerRuntimeStore(context).configure(config.toString()));
        capacitor.edit().putString(WidgetTimerPreferences.ACTIVE_DB_KEY, database).commit();
        JsonObject snapshot = new JsonObject(), days = new JsonObject(); JsonArray ids = new JsonArray();
        ids.add("habit-1"); days.add(DailyWidgetStore.today(), ids);
        snapshot.addProperty("version", 1); snapshot.add("days", days);
        assertTrue(new DailyWidgetStore(context).publish(snapshot.toString()));
    }
    private static void restore(SharedPreferences prefs, String key, String value) {
        SharedPreferences.Editor edit = prefs.edit();
        if (value == null) edit.remove(key); else edit.putString(key, value);
        edit.commit();
    }
    @After public void cleanup() {
        if (db != null) db.close(); context.deleteDatabase(database);
        restore(capacitor, WidgetTimerPreferences.ACTIVE_DB_KEY, oldDatabase);
        restore(runtime, "runtime", oldRuntime);
        restore(widget, "snapshot", oldSnapshot); restore(widget, "pending", oldPending); restore(widget, "done", oldDone);
        restore(widget, "pending_ignore", oldPendingIgnore);
        restore(widget, "menu", oldMenu);
        restore(widget, "ignored", oldIgnored);
    }
    private void tap(String kind, String id, String action) {
        context.sendBroadcast(new Intent(DailyWidgetCommandReceiver.ACTION)
                .setClass(context, DailyWidgetCommandReceiver.class).setPackage(context.getPackageName())
                .putExtra("kind", kind).putExtra("id", id).putExtra("action", action)
                .putExtra("date", DailyWidgetStore.today()));
    }
    private boolean awaitStatus(String sql, long expected) throws Exception {
        db.open();
        for (int i = 0; i < 60; i++) {
            long actual = ((Number) db.query(sql, Collections.emptyList()).get(0).get("value")).longValue();
            if (actual == expected) return true;
            Thread.sleep(100);
        }
        return false;
    }
    private void awaitMenu(boolean expected) throws Exception {
        for (int i = 0; i < 60; i++) {
            if (new DailyWidgetStore(context).isMenuOpen("habit-1", DailyWidgetStore.today()) == expected) return;
            Thread.sleep(100);
        }
        fail("菜单状态未更新");
    }
    @Test public void refreshBroadcastReloadsRowsWithoutOpeningActivity() {
        Intent refresh = DailyWidgetProvider.refreshIntent(context);
        assertEquals(DailyWidgetProvider.ACTION_REFRESH, refresh.getAction());
        assertEquals(DailyWidgetProvider.class.getName(), refresh.getComponent().getClassName());
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(MainActivity.class.getName(), null, false);
        try {
            DailyWidgetViewsFactory factory = new DailyWidgetViewsFactory(context);
            factory.onCreate();
            assertTrue(factory.getCount() > 0);
            db.open();
            db.execute("UPDATE tasks SET status=2 WHERE id='task-1'", Collections.emptyList());
            db.close();
            context.sendBroadcast(refresh);
            instrumentation.waitForIdleSync();
            factory.onDataSetChanged();
            assertFalse(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "task-1".equals(row.id)));
            assertEquals(0, monitor.getHits());
        } finally { instrumentation.removeMonitor(monitor); }
    }
    @Test public void expiredProjectionUsesCurrentAccountScheduleOnly() {
        JsonObject old = new JsonObject(), days = new JsonObject();
        old.addProperty("userId", "widget-test"); old.addProperty("generation", 777);
        old.addProperty("database", database);
        days.add("2026-01-01", new JsonArray()); old.add("days", days);
        widget.edit().putString("snapshot", old.toString()).commit();
        assertTrue(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
        old.addProperty("userId", "another-user");
        widget.edit().putString("snapshot", old.toString()).commit();
        assertFalse(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
    }
    @Test public void refreshUsesCurrentLocalHabitSchedule() {
        assertTrue(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
        db.open();
        db.execute("UPDATE habits SET repeat_rule='FREQ=WEEKLY;BYDAY=XX' WHERE id='habit-1'", Collections.emptyList());
        db.close();
        context.sendBroadcast(DailyWidgetProvider.refreshIntent(context));
        assertFalse(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
        db.open();
        db.execute("UPDATE habits SET repeat_rule='FREQ=DAILY' WHERE id='habit-1'", Collections.emptyList());
        db.close();
        assertTrue(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
    }
    @Test public void ignoreTodayHidesHabitWithoutWritingCheckinOrOutbox() throws Exception {
        assertTrue(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
        tap("habit", "habit-1", "menu_open"); awaitMenu(true);
        tap("habit", "habit-1", "menu_ignore");
        for (int i = 0; i < 60 && !new DailyWidgetStore(context).isIgnored("habit-1", DailyWidgetStore.today()); i++)
            Thread.sleep(100);
        assertTrue(new DailyWidgetStore(context).isIgnored("habit-1", DailyWidgetStore.today()));
        assertNotNull(new DailyWidgetStore(context).pendingIgnore());
        assertFalse(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
        assertFalse(new DailyWidgetStore(context).isIgnored("habit-1",
                DailyWidgetStore.dayAt(System.currentTimeMillis() + 86_400_000L)));
        db.open();
        assertEquals(0, ((Number) db.query("SELECT COUNT(*) AS value FROM habit_checkins", Collections.emptyList())
                .get(0).get("value")).intValue());
        assertEquals(0, ((Number) db.query("SELECT COUNT(*) AS value FROM sync_outbox", Collections.emptyList())
                .get(0).get("value")).intValue());
        assertEquals(0, ((Number) db.query("SELECT COUNT(*) AS value FROM reward_ledger", Collections.emptyList()).get(0).get("value")).intValue());
        assertEquals(0, new DailyWidgetStore(context).pending().size());
    }
    @Test public void isolatedServerReceivesWidgetIgnoreOnce() throws Exception {
        android.os.Bundle args=InstrumentationRegistry.getArguments();
        String token=args.getString("token"),habitId=args.getString("habitId"),userId=args.getString("userId");
        Assume.assumeTrue(token!=null&&habitId!=null&&userId!=null);
        db.open();db.execute("INSERT INTO habits VALUES(?,'隔离测试',0,'local',2,'FREQ=DAILY')",Collections.singletonList(habitId));db.close();
        JsonObject config=new JsonObject();config.addProperty("serverUrl","http://10.0.2.2:18777");
        config.addProperty("authToken",token);config.addProperty("deviceId","device-widget-test");
        config.addProperty("verifiedUserId",userId);config.addProperty("generation",778);
        assertTrue(new WidgetTimerRuntimeStore(context).configure(config.toString()));
        JsonObject snapshot=new JsonObject(),days=new JsonObject();JsonArray ids=new JsonArray();ids.add(habitId);
        days.add(DailyWidgetStore.today(),ids);snapshot.addProperty("version",1);snapshot.add("days",days);
        assertTrue(new DailyWidgetStore(context).publish(snapshot.toString()));
        assertTrue(new DailyWidgetRepository(context).load().stream().anyMatch(row -> habitId.equals(row.id)));
        tap("habit",habitId,"menu_open");
        for(int i=0;i<60&&!new DailyWidgetStore(context).isMenuOpen(habitId,DailyWidgetStore.today());i++)Thread.sleep(100);
        assertTrue(new DailyWidgetStore(context).isMenuOpen(habitId,DailyWidgetStore.today()));
        tap("habit",habitId,"menu_ignore");
        for(int i=0;i<60&&!new DailyWidgetStore(context).isIgnored(habitId,DailyWidgetStore.today());i++)Thread.sleep(100);
        assertTrue(new DailyWidgetStore(context).isIgnored(habitId,DailyWidgetStore.today()));
        for(int i=0;i<100&&new DailyWidgetStore(context).pendingIgnore()!=null;i++)Thread.sleep(100);
        assertNull(new DailyWidgetStore(context).pendingIgnore());
    }
    @Test public void todayHabitShowsDateAndNeutralMenu() {
        assertEquals("今天 · " + DailyWidgetStore.today(),
                DailyWidgetProvider.titleForDay(DailyWidgetStore.today()));
        DailyWidgetRepository.Row habit = new DailyWidgetRepository(context).load().stream()
                .filter(row -> "habit-1".equals(row.id)).findFirst().get();
        assertEquals(DailyWidgetStore.today(), habit.day);
        assertEquals("今天", habit.badge);
        DailyWidgetViewsFactory factory = new DailyWidgetViewsFactory(context);
        factory.onCreate();
        for (int i = 0; i < factory.getCount(); i++) {
            ViewGroup view = (ViewGroup) factory.getViewAt(i).apply(context, null);
            TextView name = view.findViewById(R.id.daily_name);
            if (!"习惯".contentEquals(name.getText())) continue;
            TextView more = view.findViewById(R.id.daily_fail);
            assertEquals(View.VISIBLE, more.getVisibility());
            assertEquals("⋮", more.getText().toString());
            assertEquals("今天", ((TextView) view.findViewById(R.id.daily_badge)).getText().toString());
            assertEquals(View.GONE, view.findViewById(R.id.daily_confirm).getVisibility());
            assertTrue(view.indexOfChild(more) > view.indexOfChild(name));
            return;
        }
        fail("今日习惯行未渲染");
    }
    @Test public void menuNeedsSecondTapAndCanBeCancelled() throws Exception {
        tap("habit", "habit-1", "fail");
        tap("habit", "habit-1", "menu_confirm");
        InstrumentationRegistry.getInstrumentation().waitForIdleSync();
        assertEquals(0, new DailyWidgetStore(context).pending().size());
        tap("habit", "habit-1", "menu_open"); awaitMenu(true);
        assertEquals(0, new DailyWidgetStore(context).pending().size());
        DailyWidgetViewsFactory factory = new DailyWidgetViewsFactory(context);
        factory.onCreate();
        boolean menuVisible = false;
        for (int i = 0; i < factory.getCount(); i++) {
            ViewGroup view = (ViewGroup) factory.getViewAt(i).apply(context, null);
            if (!"习惯".contentEquals(((TextView) view.findViewById(R.id.daily_name)).getText())) continue;
            menuVisible = view.findViewById(R.id.daily_confirm).getVisibility() == View.VISIBLE
                    && view.findViewById(R.id.daily_cancel).getVisibility() == View.VISIBLE
                    && view.findViewById(R.id.daily_badge).getVisibility() == View.GONE;
        }
        assertTrue(menuVisible);
        tap("habit", "habit-1", "menu_cancel"); awaitMenu(false);
        tap("habit", "habit-1", "menu_confirm");
        assertEquals(0, new DailyWidgetStore(context).pending().size());
        tap("habit", "habit-1", "menu_open"); awaitMenu(true);
        context.sendBroadcast(DailyWidgetProvider.refreshIntent(context)); awaitMenu(false);
    }
    @Test public void habitCheckboxOpensChecklistAndDispatchesComplete() throws Exception {
        AtomicReference<String> script = new AtomicReference<>();
        DailyWidgetBridge bridge = new DailyWidgetBridge(context, script::set);
        DailyWidgetBridge.attach(bridge); bridge.setForeground(true); bridge.ready();
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(MainActivity.class.getName(), null, true);
        try {
            tap("habit", "habit-1", "complete");
            for (int i = 0; i < 60 && script.get() == null; i++) Thread.sleep(100);
            assertNotNull(script.get());
            assertTrue(script.get().contains("\"action\":\"complete\""));
            JsonObject command = new DailyWidgetStore(context).pending()
                    .getAsJsonObject("habit:habit-1:" + DailyWidgetStore.today());
            new DailyWidgetStore(context).ack(command.get("commandId").getAsString(), "applied");
            assertFalse(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
            for (int i = 0; i < 60 && monitor.getHits() < 1; i++) Thread.sleep(100);
            assertEquals(1, monitor.getHits());
        } finally { bridge.close(); instrumentation.removeMonitor(monitor); }
    }
    @Test public void coldHabitTapKeepsOnePendingCommandUntilAppIsReady() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(MainActivity.class.getName(), null, true);
        try {
            tap("habit", "habit-1", "complete");
            String key = "habit:habit-1:" + DailyWidgetStore.today();
            for (int i = 0; i < 60 && !new DailyWidgetStore(context).pending().has(key); i++) Thread.sleep(100);
            JsonObject first = new DailyWidgetStore(context).pending().getAsJsonObject(key);
            assertNotNull(first);
            tap("habit", "habit-1", "complete");
            for (int i = 0; i < 60 && monitor.getHits() < 2; i++) Thread.sleep(100);
            assertEquals(first.get("commandId").getAsString(), new DailyWidgetStore(context).pending()
                    .getAsJsonObject(key).get("commandId").getAsString());
            assertEquals(1, new DailyWidgetStore(context).pending().size());
            assertEquals(2, monitor.getHits());
        } finally { instrumentation.removeMonitor(monitor); }
    }
    @Test public void backgroundTaskCompletesWithoutOpeningActivity() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(MainActivity.class.getName(), null, false);
        try {
            tap("task", "task-1", "complete");
            assertTrue(awaitStatus("SELECT status AS value FROM tasks WHERE id='task-1'", 2));
            for (int i = 0; i < 60 && !new DailyWidgetStore(context).isDone("task", "task-1", DailyWidgetStore.today()); i++)
                Thread.sleep(100);
            assertTrue(new DailyWidgetStore(context).isDone("task", "task-1", DailyWidgetStore.today()));
            assertEquals(0, monitor.getHits());
            assertEquals(0, new DailyWidgetStore(context).pending().size());
        } finally { instrumentation.removeMonitor(monitor); }
    }
    @Test public void foregroundBridgeDispatchesWithoutOpeningActivity() throws Exception {
        AtomicReference<String> script = new AtomicReference<>();
        DailyWidgetBridge bridge = new DailyWidgetBridge(context, script::set);
        DailyWidgetBridge.attach(bridge); bridge.setForeground(true); bridge.ready();
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(MainActivity.class.getName(), null, false);
        try {
            tap("task", "task-1", "complete");
            for (int i = 0; i < 60 && script.get() == null; i++) Thread.sleep(100);
            assertNotNull(script.get());
            assertTrue(script.get().contains("\"action\":\"complete\""));
            assertEquals(0, monitor.getHits());
        } finally { bridge.close(); instrumentation.removeMonitor(monitor); }
    }
    @Test public void offlineHabitFailureStaysVisibleForSameIdRetry() throws Exception {
        tap("habit", "habit-1", "menu_open");
        for (int i = 0; i < 60 && !new DailyWidgetStore(context).isMenuOpen("habit-1", DailyWidgetStore.today()); i++)
            Thread.sleep(100);
        assertTrue(new DailyWidgetStore(context).pending().size() == 0);
        tap("habit", "habit-1", "menu_confirm");
        DailyWidgetStore store = new DailyWidgetStore(context);
        String key = "habit:habit-1:" + DailyWidgetStore.today();
        for (int i = 0; i < 60; i++) {
            if (store.pending().has(key) && store.pending().getAsJsonObject(key).has("lastResult")) break;
            Thread.sleep(100);
        }
        assertEquals("failed", store.pending().getAsJsonObject(key).get("lastResult").getAsString());
        String id = store.pending().getAsJsonObject(key).get("commandId").getAsString();
        assertEquals(id, store.claim("habit", "habit-1", DailyWidgetStore.today(), "fail")
                .get("commandId").getAsString());
        assertNull(store.claim("habit", "habit-1", DailyWidgetStore.today(), "complete"));
        assertFalse(store.isDone("habit", "habit-1", DailyWidgetStore.today()));
        assertTrue(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
    }
    @Test public void confirmedHabitFailureDisappearsWithoutOpeningActivity() throws Exception {
        try (ServerSocket server = new ServerSocket(0)) {
            JsonObject config = new JsonObject();
            config.addProperty("serverUrl", "http://127.0.0.1:" + server.getLocalPort());
            config.addProperty("authToken", "test"); config.addProperty("deviceId", "device-widget-test");
            config.addProperty("verifiedUserId", "widget-test"); config.addProperty("generation", 777);
            assertTrue(new WidgetTimerRuntimeStore(context).configure(config.toString()));
            Thread responder = new Thread(() -> {
                try (Socket socket = server.accept()) {
                    StringBuilder header = new StringBuilder(); int next;
                    while ((next = socket.getInputStream().read()) >= 0 && header.length() < 4096) {
                        header.append((char) next);
                        if (header.toString().endsWith("\r\n\r\n")) break;
                    }
                    byte[] body = "{\"status\":\"confirmed\"}".getBytes(StandardCharsets.UTF_8);
                    socket.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                            + body.length + "\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.UTF_8));
                    socket.getOutputStream().write(body); socket.getOutputStream().flush();
                } catch (Exception error) { throw new RuntimeException(error); }
            });
            responder.start();
            Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
            Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(MainActivity.class.getName(), null, false);
            try {
                tap("habit", "habit-1", "menu_open");
                for (int i = 0; i < 60 && !new DailyWidgetStore(context).isMenuOpen("habit-1", DailyWidgetStore.today()); i++)
                    Thread.sleep(100);
                tap("habit", "habit-1", "menu_confirm");
                for (int i = 0; i < 60 && !new DailyWidgetStore(context).isDone("habit", "habit-1", DailyWidgetStore.today()); i++)
                    Thread.sleep(100);
                assertTrue(new DailyWidgetStore(context).isDone("habit", "habit-1", DailyWidgetStore.today()));
                assertFalse(new DailyWidgetRepository(context).load().stream().anyMatch(row -> "habit-1".equals(row.id)));
                assertEquals(0, monitor.getHits());
            } finally { instrumentation.removeMonitor(monitor); }
            responder.join(1000);
        }
    }
}
