package com.mytimelogger.app;

import android.content.Context;
import com.google.gson.GsonBuilder;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.UUID;

final class DailyWidgetTaskWriter {
    static String now() {
        SimpleDateFormat value = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT);
        value.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
        return value.format(new Date());
    }
    static String complete(Context context, String database, String id) {
        if (database == null || database.isEmpty() || database.contains("/") || database.contains("\\")
                || !context.getDatabasePath(database).isFile()) return "failed";
        SqliteConnection db = new SqliteConnection(context, database);
        try {
            db.open();
            String[] outcome = {"failed"};
            db.transaction(() -> {
                List<Map<String, Object>> rows = db.query("SELECT * FROM tasks WHERE id=? AND deleted_at IS NULL", Collections.singletonList(id));
                if (rows.size() != 1) return;
                Map<String, Object> task = rows.get(0);
                int status = ((Number) task.get("status")).intValue();
                if (status == 2) { outcome[0] = "applied"; return; }
                if (status != 0) return;
                String timestamp = now();
                db.execute("UPDATE tasks SET status=2,updated_at=?,pushed_at=NULL WHERE id=? AND status=0", Arrays.asList(timestamp, id));
                for (Map<String, Object> reward : db.query(
                        "SELECT id,title FROM rewards WHERE unlock_task_id=? AND is_active=1", Collections.singletonList(id))) {
                    String ledgerId = "ledger_" + UUID.randomUUID();
                    String description = "任务自动解锁兑换: " + reward.get("title")
                            + " [来自任务完成: " + task.get("title") + "]";
                    db.execute("INSERT INTO reward_ledger (id,amount,source_type,source_id,description,created_at,updated_at) "
                                    + "VALUES (?,0,'reward_unlock',?,?,?,?)",
                            Arrays.asList(ledgerId, String.valueOf(reward.get("id")), description, timestamp, timestamp));
                }
                String deviceId = deviceId(db);
                Map<String, Object> updated = db.query("SELECT * FROM tasks WHERE id=?", Collections.singletonList(id)).get(0);
                String payload = new GsonBuilder().serializeNulls().create().toJson(updated);
                List<Map<String, Object>> pending = db.query("SELECT id FROM sync_outbox WHERE table_name='tasks' "
                        + "AND record_id=? AND status IN ('pending','failed') ORDER BY id DESC LIMIT 1", Collections.singletonList(id));
                if (pending.isEmpty()) {
                    String changeId = deviceId + "_" + UUID.randomUUID();
                    db.execute("INSERT INTO sync_outbox (change_id,device_id,table_name,record_id,operation,base_version,"
                                    + "payload_json,status,retry_count,created_at,updated_at) VALUES (?,?,'tasks',?,'upsert',NULL,?,'pending',0,?,?)",
                            Arrays.asList(changeId, deviceId, id, payload, timestamp, timestamp));
                } else {
                    db.execute("UPDATE sync_outbox SET operation='upsert',payload_json=?,base_version=NULL,status='pending',"
                                    + "last_error=NULL,updated_at=? WHERE id=?",
                            Arrays.asList(payload, timestamp, pending.get(0).get("id")));
                }
                outcome[0] = "pending_sync";
            });
            return outcome[0];
        } catch (RuntimeException ignored) { return "failed"; }
        finally { db.close(); }
    }
    private static String deviceId(SqliteConnection db) {
        List<Map<String, Object>> rows = db.query("SELECT value FROM system_config WHERE key='device_id'", Collections.emptyList());
        if (rows.size() != 1 || rows.get(0).get("value") == null) throw new IllegalStateException("missing_device_id");
        return String.valueOf(rows.get(0).get("value"));
    }
}
