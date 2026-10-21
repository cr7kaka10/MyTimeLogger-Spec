package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.gson.JsonParser;
import java.util.Collections;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class DailyWidgetTaskWriterTest {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    private final String name = "daily-widget-task-test.db";
    private SqliteConnection db;
    @Before public void setup() {
        context.deleteDatabase(name);
        db = new SqliteConnection(context, name); db.open();
        db.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,status INTEGER,deleted_at TEXT,title TEXT,updated_at TEXT,pushed_at TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE rewards(id TEXT,title TEXT,unlock_task_id TEXT,is_active INTEGER)", Collections.emptyList());
        db.execute("CREATE TABLE reward_ledger(id TEXT,amount REAL,source_type TEXT,source_id TEXT,description TEXT,created_at TEXT,updated_at TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE system_config(key TEXT,value TEXT)", Collections.emptyList());
        db.execute("CREATE TABLE sync_outbox(id INTEGER PRIMARY KEY,change_id TEXT,device_id TEXT,table_name TEXT,record_id TEXT,operation TEXT,base_version TEXT,payload_json TEXT,status TEXT,retry_count INTEGER,created_at TEXT,updated_at TEXT,last_error TEXT)", Collections.emptyList());
        db.execute("INSERT INTO tasks(id,status,title) VALUES('task-1',0,'任务')", Collections.emptyList());
        db.execute("INSERT INTO rewards VALUES('reward-1','奖励','task-1',1)", Collections.emptyList());
        db.execute("INSERT INTO system_config VALUES('device_id','device-test')", Collections.emptyList());
        db.close();
    }
    @After public void cleanup() { if (db != null) db.close(); context.deleteDatabase(name); }
    private long count(String table) {
        return ((Number) db.query("SELECT COUNT(*) AS n FROM " + table, Collections.emptyList()).get(0).get("n")).longValue();
    }
    @Test public void completionMirrorsRewardAndOutboxOnce() {
        assertEquals("pending_sync", DailyWidgetTaskWriter.complete(context, name, "task-1"));
        assertEquals("applied", DailyWidgetTaskWriter.complete(context, name, "task-1"));
        db.open();
        assertEquals(2L, db.query("SELECT status FROM tasks WHERE id='task-1'", Collections.emptyList()).get(0).get("status"));
        assertEquals(1L, count("reward_ledger")); assertEquals(1L, count("sync_outbox"));
        String payload = (String) db.query("SELECT payload_json FROM sync_outbox", Collections.emptyList()).get(0).get("payload_json");
        assertEquals(2, JsonParser.parseString(payload).getAsJsonObject().get("status").getAsInt());
        assertEquals("reward_unlock", db.query("SELECT source_type FROM reward_ledger", Collections.emptyList()).get(0).get("source_type"));
    }
    @Test public void missingDeviceRollsBackTaskAndReward() {
        db.open(); db.execute("DELETE FROM system_config", Collections.emptyList()); db.close();
        assertEquals("failed", DailyWidgetTaskWriter.complete(context, name, "task-1"));
        db.open();
        assertEquals(0L, db.query("SELECT status FROM tasks WHERE id='task-1'", Collections.emptyList()).get(0).get("status"));
        assertEquals(0L, count("reward_ledger")); assertEquals(0L, count("sync_outbox"));
    }
}
