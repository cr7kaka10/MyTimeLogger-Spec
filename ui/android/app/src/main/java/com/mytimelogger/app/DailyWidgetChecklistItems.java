package com.mytimelogger.app;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
final class DailyWidgetChecklistItems {
    static final class Entry {
        final String id, title; final int status;
        final long sortOrder;
        Entry(String id, String title, int status, long sortOrder) {
            this.id = id; this.title = title; this.status = status; this.sortOrder = sortOrder;
        }
        boolean done() { return status == 2; }
    }
    static List<Entry> parse(String rawJson) {
        if (rawJson == null || rawJson.isEmpty()) return Collections.emptyList();
        try {
            JsonObject task = JsonParser.parseString(rawJson).getAsJsonObject();
            JsonElement value = task.get("items");
            if (value == null || !value.isJsonArray()) return Collections.emptyList();
            JsonArray source = value.getAsJsonArray();
            List<Entry> result = new ArrayList<>();
            for (int index = 0; index < source.size(); index++) {
                JsonElement item = source.get(index);
                if (!item.isJsonObject()) continue;
                JsonObject data = item.getAsJsonObject();
                JsonPrimitive id = primitive(data, "id"), title = primitive(data, "title");
                JsonPrimitive status = primitive(data, "status");
                if (id == null || !id.isString() || id.getAsString().isEmpty()
                        || title == null || !title.isString() || status == null || !status.isNumber()) continue;
                int state = status.getAsInt();
                if (status.getAsDouble() != state) continue;
                JsonPrimitive order = primitive(data, "sortOrder");
                long sort = order != null && order.isNumber() ? order.getAsLong() : index;
                result.add(new Entry(id.getAsString(), title.getAsString(), state, sort));
            }
            result.sort(Comparator.comparingLong(entry -> entry.sortOrder));
            return result;
        } catch (RuntimeException ignored) { return Collections.emptyList(); }
    }
    private static JsonPrimitive primitive(JsonObject value, String key) {
        JsonElement item = value.get(key);
        return item != null && item.isJsonPrimitive() ? item.getAsJsonPrimitive() : null;
    }
}
