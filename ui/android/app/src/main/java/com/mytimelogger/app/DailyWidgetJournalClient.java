package com.mytimelogger.app;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class DailyWidgetJournalClient {
    interface Transport { Response request(String method, String url, String token, String body) throws Exception; }
    static final class Response {
        final int code; final String body;
        Response(int code, String body) { this.code = code; this.body = body; }
    }
    private final Transport transport;
    DailyWidgetJournalClient() { this(new HttpTransport()); }
    DailyWidgetJournalClient(Transport transport) { this.transport = transport; }

    Boolean promptEnabled(WidgetTimerRuntimeStore.Config runtime, String habitId) {
        if (runtime == null) return null;
        try {
            Response response = transport.request("GET", runtime.serverUrl + "/api/habits", runtime.authToken, null);
            if (response.code != 200) return null;
            JsonArray habits = JsonParser.parseString(response.body).getAsJsonObject().getAsJsonArray("habits");
            for (int i = 0; i < habits.size(); i++) {
                JsonObject habit = habits.get(i).getAsJsonObject();
                if (habitId.equals(habit.get("id").getAsString()))
                    return "local".equals(habit.get("source").getAsString())
                            && habit.get("is_active").getAsInt() == 0
                            && habit.get("journal_prompt_enabled").getAsInt() == 1;
            }
        } catch (Exception ignored) { return null; }
        return null;
    }

    boolean save(WidgetTimerRuntimeStore.Config runtime, String habitId, String day, String note) {
        if (runtime == null || !habitId.matches("[A-Za-z0-9._:-]{1,128}") || !day.matches("\\d{4}-\\d{2}-\\d{2}")) return false;
        JsonObject body = new JsonObject(); body.addProperty("note", note);
        try {
            Response response = transport.request("PUT", runtime.serverUrl + "/api/habits/" + habitId
                    + "/checkins/" + day + "/journal", runtime.authToken, body.toString());
            return response.code == 200;
        } catch (Exception ignored) { return false; }
    }

    boolean disable(WidgetTimerRuntimeStore.Config runtime, String habitId) {
        if (runtime == null || !habitId.matches("[A-Za-z0-9._:-]{1,128}")) return false;
        try {
            Response response = transport.request("PUT", runtime.serverUrl + "/api/habits/" + habitId
                    + "/journal-prompt", runtime.authToken, "{\"enabled\":false}");
            return response.code == 200;
        } catch (Exception ignored) { return false; }
    }

    private static final class HttpTransport implements Transport {
        public Response request(String method, String url, String token, String body) throws Exception {
            HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
            try {
                connection.setRequestMethod(method); connection.setConnectTimeout(3500); connection.setReadTimeout(3500);
                connection.setRequestProperty("Authorization", "Bearer " + token);
                if (body != null) { connection.setRequestProperty("Content-Type", "application/json"); connection.setDoOutput(true);
                    try (OutputStream out = connection.getOutputStream()) { out.write(body.getBytes(StandardCharsets.UTF_8)); } }
                int code = connection.getResponseCode(); InputStream input = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
                if (input == null) return new Response(code, "");
                try (InputStream stream = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                    byte[] bytes = new byte[2048]; int count;
                    while ((count = stream.read(bytes)) >= 0) out.write(bytes, 0, count);
                    return new Response(code, out.toString("UTF-8"));
                }
            } finally { connection.disconnect(); }
        }
    }
}
