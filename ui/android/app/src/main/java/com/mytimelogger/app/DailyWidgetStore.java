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
            String day = today();
            if (!ownerMatches(value, runtime.verifiedUserId, runtime.generation, database)) return null;
            JsonObject days = value.getAsJsonObject("days");
            days.add(day, DailyWidgetSchedule.ids(context, database, day));
            return value;
        } catch (Exception ignored) { return null; }
    }
    static boolean ownerMatches(JsonObject value, String userId, long generation, String database) {
        try { return value != null && value.get("generation").getAsLong() == generation
                && userId.equals(value.get("userId").getAsString())
                && database.equals(value.get("database").getAsString())
                && value.getAsJsonObject("days") != null; }
        catch (Exception ignored) { return false; }
    }
    static boolean matches(JsonObject value, String userId, long generation, String database, String day) {
        try { return ownerMatches(value, userId, generation, database) && value.getAsJsonObject("days").has(day); }
        catch (Exception ignored) { return false; }
    }
    static boolean ignored(JsonObject snapshot, JsonObject hidden, String day, String id) {
        try { return ownerMatches(snapshot, string(hidden, "userId"), hidden.get("generation").getAsLong(), string(hidden, "database"))
                && day.equals(string(hidden, "date")) && hidden.getAsJsonObject("ids").has(id); }
        catch (RuntimeException ignored) { return false; }
    }
    boolean isIgnored(String id, String day) { return isIgnored(id, day, null); }
    boolean isIgnored(String id, String day, Boolean authoritative) {
        if (authoritative != null) return authoritative;
        JsonObject owner = snapshot(), pending = readObject("pending_ignore");
        return ignored(owner, readObject("ignored"), day, id)
                || (pending.has(id) && matchesCommand(owner, pending.getAsJsonObject(id), day));
    }
    boolean ignoreHabit(String id, String day) { synchronized (DailyWidgetStore.class) {
        JsonObject owner = snapshot();
        if (owner == null || !today().equals(day) || id == null || id.isEmpty()) return false;
        JsonObject hidden = readObject("ignored");
        if (!ownerMatches(owner, string(hidden, "userId"),
                hidden.has("generation") ? hidden.get("generation").getAsLong() : -1, string(hidden, "database"))
                || !day.equals(string(hidden, "date")) || hidden.getAsJsonObject("ids") == null) {
            hidden = new JsonObject(); hidden.addProperty("userId", string(owner, "userId"));
            hidden.addProperty("generation", owner.get("generation").getAsLong());
            hidden.addProperty("database", string(owner, "database")); hidden.addProperty("date", day);
            hidden.add("ids", new JsonObject());
        }
        hidden.getAsJsonObject("ids").addProperty(id, true);
        JsonObject pending = readObject("pending_ignore");
        JsonObject command = pending.has(id) ? pending.getAsJsonObject(id) : new JsonObject();
        if (!matchesCommand(owner, command, day)) {
            command = new JsonObject();
            command.addProperty("id", id); command.addProperty("date", day);
            command.addProperty("commandId", "daily-ignore-" + UUID.randomUUID());
            command.addProperty("userId", string(owner, "userId"));
            command.addProperty("generation", owner.get("generation").getAsLong());
            command.addProperty("database", string(owner, "database"));
        }
        pending.add(id, command);
        return values.edit().putString("ignored", hidden.toString())
                .putString("pending_ignore", pending.toString()).commit();
    } }
    JsonObject pendingIgnore() {
        JsonObject owner = snapshot(), pending = readObject("pending_ignore");
        if (owner == null) return null;
        for (String key : pending.keySet()) {
            JsonObject command = pending.getAsJsonObject(key);
            if (matchesCommand(owner, command, today())) return command;
        }
        return null;
    }
    void ackIgnore(String commandId, boolean accepted) { synchronized (DailyWidgetStore.class) {
        JsonObject pending = readObject("pending_ignore");
        for (String key : pending.keySet()) {
            JsonObject command = pending.getAsJsonObject(key);
            if (!commandId.equals(string(command, "commandId"))) continue;
            pending.remove(key);
            SharedPreferences.Editor editor = values.edit().putString("pending_ignore", pending.toString());
            if (!accepted) {
                JsonObject hidden = readObject("ignored");
                JsonObject ids = hidden.getAsJsonObject("ids");
                if (ids != null) { ids.remove(key); editor.putString("ignored", hidden.toString()); }
            }
            editor.commit(); return;
        }
    } }
    static boolean matchesCommand(JsonObject snapshot, JsonObject command, String day) {
        try {
            return snapshot != null && command != null && day.equals(string(command, "date"))
                    && string(snapshot, "userId").equals(string(command, "userId"))
                    && snapshot.get("generation").getAsLong() == command.get("generation").getAsLong()
                    && (!command.has("database") || string(snapshot, "database").equals(string(command, "database")));
        } catch (RuntimeException ignored) { return false; }
    }
    boolean publish(String raw) { synchronized (DailyWidgetStore.class) { return publishLocked(raw); } }
    private boolean publishLocked(String raw) {
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
                editor.putString("pending_ignore", rebasePending(readObject("pending_ignore"), today(), runtime.generation).toString());
            } else editor.remove("pending").remove("pending_ignore").remove("done").remove("expanded_items").remove("ignored");
            return editor.commit();
        } catch (Exception ignored) { return false; }
    }
    JsonObject claim(String kind, String id, String day) { return claim(kind, id, day, "complete"); }
    JsonObject claim(String kind, String id, String day, String action) {
        synchronized (DailyWidgetStore.class) { return claimLocked(kind, id, day, action); }
    }
    private JsonObject claimLocked(String kind, String id, String day, String action) {
        JsonObject snapshot = snapshot();
        if (snapshot == null || !today().equals(day) || !("habit".equals(kind) || "task".equals(kind))) return null;
        if (!("complete".equals(action) || ("habit".equals(kind) && "fail".equals(action)))) return null;
        if (id == null || id.isEmpty() || id.length() > 128) return null;
        JsonObject pending = readObject("pending");
        String key = kind + ":" + id + ":" + day;
        JsonObject existing = existingClaim(pending, readObject("done"), key);
        if (existing != null) {
            String previousAction = string(existing, "action");
            return action.equals(previousAction.isEmpty() ? "complete" : previousAction) ? existing : null;
        }
        if (readObject("done").has(key)) return null;
        JsonObject command = new JsonObject();
        command.addProperty("kind", kind); command.addProperty("id", id);
        command.addProperty("action", action);
        command.addProperty("date", day); command.addProperty("commandId", "daily-" + UUID.randomUUID());
        command.addProperty("userId", snapshot.get("userId").getAsString());
        command.addProperty("generation", snapshot.get("generation").getAsLong());
        command.addProperty("database", snapshot.get("database").getAsString());
        pending.add(key, command);
        return values.edit().putString("pending", pending.toString()).commit() ? command : null;
    }
    static JsonObject existingClaim(JsonObject pending, JsonObject done, String key) {
        return done.has(key) ? null : pending.has(key) ? pending.getAsJsonObject(key) : null;
    }
    synchronized JsonObject pending() { return readObject("pending"); }
    void ack(String commandId, String result) {
        synchronized (DailyWidgetStore.class) { ackLocked(commandId, result); }
    }
    private void ackLocked(String commandId, String result) {
        JsonObject pending = readObject("pending");
        String matchedKey = null;
        for (String key : pending.keySet()) {
            JsonObject command = pending.getAsJsonObject(key);
            if (commandId.equals(command.get("commandId").getAsString())) { matchedKey = key; break; }
        }
        if (matchedKey == null) return;
        if ("failed".equals(result)) {
            pending.getAsJsonObject(matchedKey).addProperty("lastResult", "failed");
            values.edit().putString("pending", pending.toString()).commit();
            return;
        }
        if ("rejected".equals(result)) {
            pending.remove(matchedKey);
            values.edit().putString("pending", pending.toString()).commit();
            return;
        }
        if (!("applied".equals(result) || "pending_sync".equals(result))) return;
        JsonObject done = readObject("done");
        done.addProperty(matchedKey, result);
        pending.remove(matchedKey);
        values.edit().putString("done", done.toString()).putString("pending", pending.toString()).commit();
    }
    boolean isDone(String kind, String id, String day) { return readObject("done").has(kind + ":" + id + ":" + day); }
    boolean isItemsExpanded(String id, String day) {
        return expandedMatches(snapshot(), readObject("expanded_items"), id, day);
    }
    boolean toggleItems(String id, String day) {
        synchronized (DailyWidgetStore.class) {
            JsonObject owner = snapshot();
            if (owner == null || id == null || id.isEmpty() || !today().equals(day)) return false;
            if (expandedMatches(owner, readObject("expanded_items"), id, day))
                return values.edit().remove("expanded_items").commit();
            JsonObject state = new JsonObject();
            state.addProperty("userId", string(owner, "userId"));
            state.addProperty("generation", owner.get("generation").getAsLong());
            state.addProperty("database", string(owner, "database"));
            state.addProperty("date", day); state.addProperty("id", id);
            return values.edit().putString("expanded_items", state.toString()).commit();
        }
    }
    static boolean expandedMatches(JsonObject owner, JsonObject state, String id, String day) {
        try {
            return owner != null && state != null && day.equals(today())
                    && string(owner, "userId").equals(string(state, "userId"))
                    && owner.get("generation").getAsLong() == state.get("generation").getAsLong()
                    && string(owner, "database").equals(string(state, "database"))
                    && day.equals(string(state, "date")) && id.equals(string(state, "id"));
        } catch (RuntimeException ignored) { return false; }
    }
    boolean openMenu(String id, String day) {
        synchronized (DailyWidgetStore.class) {
            JsonObject owner = snapshot();
            if (owner == null || !today().equals(day) || id == null || id.isEmpty()) return false;
            JsonObject menu = new JsonObject();
            menu.addProperty("userId", owner.get("userId").getAsString());
            menu.addProperty("generation", owner.get("generation").getAsLong());
            menu.addProperty("database", owner.get("database").getAsString());
            menu.addProperty("date", day); menu.addProperty("id", id);
            menu.addProperty("expiresAt", System.currentTimeMillis() + 120_000);
            return values.edit().putString("menu", menu.toString()).commit();
        }
    }
    boolean isMenuOpen(String id, String day) {
        return today().equals(day) && menuMatches(snapshot(), readObject("menu"), id, day, System.currentTimeMillis());
    }
    boolean consumeMenu(String id, String day) {
        synchronized (DailyWidgetStore.class) {
            boolean valid = isMenuOpen(id, day);
            values.edit().remove("menu").commit();
            return valid;
        }
    }
    void clearMenu() { values.edit().remove("menu").commit(); }
    static boolean menuMatches(JsonObject owner, JsonObject menu, String id, String day, long now) {
        try {
            return owner != null && id.equals(string(menu, "id")) && day.equals(string(menu, "date"))
                    && matchesCommand(owner, menu, day) && menu.get("expiresAt").getAsLong() > now;
        } catch (RuntimeException ignored) { return false; }
    }
    String pendingState(String kind, String id, String day) {
        try {
            JsonObject pending = readObject("pending");
            String key = kind + ":" + id + ":" + day;
            if (!pending.has(key)) return "";
            return "failed".equals(string(pending.getAsJsonObject(key), "lastResult")) ? "failed" : "pending";
        } catch (RuntimeException ignored) { return ""; }
    }
    void clear() { synchronized (DailyWidgetStore.class) { values.edit().clear().commit(); } }
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
                if (!command.has("action")) command.addProperty("action", "complete");
                command.addProperty("generation", generation);
                pending.add(key, command);
            } catch (RuntimeException ignored) { }
        }
        return pending;
    }
}
