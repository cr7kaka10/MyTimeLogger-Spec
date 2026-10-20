package com.mytimelogger.app;

import android.content.Context;
import android.content.SharedPreferences;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.UUID;

final class DailyWidgetStore {
    private static final String PREFS = "mtl_daily_widget_v1";
    private final Context context;
    private final SharedPreferences values;
    DailyWidgetStore(Context context) {
        this.context = context.getApplicationContext();
        values = this.context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
    static String today() { return dayAt(System.currentTimeMillis()); }
    static String dayAt(long epochMs) {
        SimpleDateFormat date = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        date.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
        return date.format(new Date(epochMs));
    }
    private WidgetTimerRuntimeStore.Config runtime() { return new WidgetTimerRuntimeStore(context).read(); }
    private String databaseName() { return new WidgetTimerPreferences(context).loadActiveDatabaseName(); }
    JsonObject snapshot() {
        WidgetTimerRuntimeStore.Config runtime = runtime();
        String database = databaseName();
        if (runtime == null || database == null) return null;
        try {
            JsonObject value = JsonParser.parseString(values.getString("snapshot", "")).getAsJsonObject();
            return matches(value, runtime.verifiedUserId, runtime.generation, database, today()) ? value : null;
        } catch (Exception ignored) { return null; }
    }
    static boolean matches(JsonObject value, String userId, long generation, String database, String day) {
        try { return value != null && value.get("generation").getAsLong() == generation
                && userId.equals(value.get("userId").getAsString())
                && database.equals(value.get("database").getAsString())
                && value.getAsJsonObject("days").has(day); }
        catch (Exception ignored) { return false; }
    }
    boolean publish(String raw) {
        WidgetTimerRuntimeStore.Config runtime = runtime();
        String database = databaseName();
        if (runtime == null || database == null || raw == null || raw.length() > 500_000) return false;
        try {
            JsonObject input = JsonParser.parseString(raw).getAsJsonObject();
            if (input.get("version").getAsInt() != 1) return false;
            JsonObject days = input.getAsJsonObject("days");
            if (days == null || days.size() > 90 || !days.has(today())) return false;
            for (String day : days.keySet()) {
                if (!day.matches("\\d{4}-\\d{2}-\\d{2}")) return false;
                JsonArray ids = days.getAsJsonArray(day);
                if (ids == null || ids.size() > 300) return false;
            }
            JsonObject snapshot = new JsonObject();
            snapshot.addProperty("userId", runtime.verifiedUserId);
            snapshot.addProperty("generation", runtime.generation);
            snapshot.addProperty("database", database);
            snapshot.add("days", days);
            JsonObject previous = readObject("snapshot");
            boolean sameAccount = runtime.verifiedUserId.equals(string(previous, "userId"))
                    && database.equals(string(previous, "database"));
            SharedPreferences.Editor editor = values.edit().putString("snapshot", snapshot.toString());
            if (sameAccount) {
                editor.putString("pending", rebasePending(readObject("pending"), today(), runtime.generation).toString());
            } else editor.remove("pending").remove("done");
            return editor.commit();
        } catch (Exception ignored) { return false; }
    }
    synchronized JsonObject claim(String kind, String id, String day) {
        JsonObject snapshot = snapshot();
        if (snapshot == null || !today().equals(day) || !("habit".equals(kind) || "task".equals(kind))) return null;
        if (id == null || id.isEmpty() || id.length() > 128) return null;
        JsonObject pending = readObject("pending");
        String key = kind + ":" + id + ":" + day;
        JsonObject existing = existingClaim(pending, readObject("done"), key);
        if (existing != null || readObject("done").has(key)) return existing;
        JsonObject command = new JsonObject();
        command.addProperty("kind", kind); command.addProperty("id", id);
        command.addProperty("date", day); command.addProperty("commandId", "daily-" + UUID.randomUUID());
        command.addProperty("userId", snapshot.get("userId").getAsString());
        command.addProperty("generation", snapshot.get("generation").getAsLong());
        pending.add(key, command);
        values.edit().putString("pending", pending.toString()).commit();
        return command;
    }
    static JsonObject existingClaim(JsonObject pending, JsonObject done, String key) {
        return done.has(key) ? null : pending.has(key) ? pending.getAsJsonObject(key) : null;
    }
    synchronized JsonObject pending() { return readObject("pending"); }
    synchronized void ack(String commandId, String result) {
        JsonObject pending = readObject("pending");
        String matchedKey = null;
        for (String key : pending.keySet()) {
            JsonObject command = pending.getAsJsonObject(key);
            if (commandId.equals(command.get("commandId").getAsString())) { matchedKey = key; break; }
        }
        if (matchedKey == null || !("applied".equals(result) || "pending_sync".equals(result))) return;
        JsonObject done = readObject("done");
        done.addProperty(matchedKey, result);
        pending.remove(matchedKey);
        values.edit().putString("done", done.toString()).putString("pending", pending.toString()).commit();
    }
    boolean isDone(String kind, String id, String day) { return readObject("done").has(kind + ":" + id + ":" + day); }
    void clear() { values.edit().clear().commit(); }
    private JsonObject readObject(String key) {
        try { return JsonParser.parseString(values.getString(key, "{}")).getAsJsonObject(); }
        catch (Exception ignored) { return new JsonObject(); }
    }
    private static String string(JsonObject value, String key) {
        try { return value.get(key).getAsString(); }
        catch (RuntimeException ignored) { return ""; }
    }
    static JsonObject rebasePending(JsonObject old, String day, long generation) {
        JsonObject pending = new JsonObject();
        for (String key : old.keySet()) {
            try {
                JsonObject command = old.getAsJsonObject(key);
                if (!day.equals(string(command, "date"))) continue;
                command.addProperty("generation", generation);
                pending.add(key, command);
            } catch (RuntimeException ignored) { }
        }
        return pending;
    }
}
