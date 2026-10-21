package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
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
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class DailyWidgetReceiverTest {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    private final String database = "daily-widget-receiver-test.db";
    private SharedPreferences capacitor, runtime, widget;
    private String oldDatabase, oldRuntime, oldSnapshot, oldPending, oldDone;
    private SqliteConnection db;
    @Before public void setup() {
        capacitor = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE);
        runtime = context.getSharedPreferences("mtl_widget_runtime_v1", Context.MODE_PRIVATE);
        widget = context.getSharedPreferences("mtl_daily_widget_v1", Context.MODE_PRIVATE);
        oldDatabase = capacitor.getString(WidgetTimerPreferences.ACTIVE_DB_KEY, null);
        oldRuntime = runtime.getString("runtime", null);
        oldSnapshot = widget.getString("snapshot", null); oldPending = widget.getString("pending", null);
        oldDone = widget.getString("done", null);
        context.deleteDatabase(database);
        db = new SqliteConnection(context, database); db.open();
        db.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,status INTEGER,deleted_at TEXT,title TEXT,due_date TEXT,priority INTEGER,updated_at TEXT,pushed_at TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE habits(id TEXT,name TEXT,is_active INTEGER,source TEXT,sort_order INTEGER)", Collections.emptyList());
        db.execute("CREATE TABLE habit_checkins(habit_id TEXT,status INTEGER,checkin_date TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE rewards(id TEXT,title TEXT,unlock_task_id TEXT,is_active INTEGER)", Collections.emptyList());
        db.execute("CREATE TABLE reward_ledger(id TEXT,amount REAL,source_type TEXT,source_id TEXT,description TEXT,created_at TEXT,updated_at TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE system_config(key TEXT,value TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE sync_outbox(id INTEGER PRIMARY KEY,change_id TEXT,device_id TEXT,table_name TEXT,record_id TEXT,operation TEXT,base_version TEXT,payload_json TEXT,status TEXT,retry_count INTEGER,created_at TEXT,updated_at TEXT,last_error TEXT)", Collections.emptyList());
        db.execute("INSERT INTO system_config VALUES('device_id','device-widget-test')", Collections.emptyList());
        db.execute("INSERT INTO tasks(id,status,title,due_date) VALUES('task-1',0,'任务',?)", Collections.singletonList(DailyWidgetStore.today()));
        db.execute("INSERT INTO habits VALUES('habit-1','习惯',0,'local',1)", Collections.emptyList());
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
        tap("habit", "habit-1", "fail");
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
                tap("habit", "habit-1", "fail");
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
