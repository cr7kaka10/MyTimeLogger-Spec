package com.mytimelogger.app;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class DailyWidgetHabitClient {
    interface Transport { Response post(String url, String token, String body) throws Exception; }
    static final class Response {
        final int code; final String body;
        Response(int code, String body) { this.code = code; this.body = body; }
    }
    private final Transport transport;
    DailyWidgetHabitClient() { this(new HttpTransport()); }
    DailyWidgetHabitClient(Transport transport) { this.transport = transport; }

    String apply(WidgetTimerRuntimeStore.Config runtime, JsonObject command) {
        if (runtime == null || command == null) return "failed";
        try {
            JsonObject body = new JsonObject();
            body.addProperty("habit_id", command.get("id").getAsString());
            body.addProperty("date", command.get("date").getAsString());
            body.addProperty("desired_status", command.has("action") && "fail".equals(command.get("action").getAsString()) ? 1 : 2);
            body.addProperty("idempotency_key", command.get("commandId").getAsString());
            Response response = transport.post(runtime.serverUrl + "/api/habits/checkin-commands", runtime.authToken, body.toString());
            if (response.code == 401 || response.code == 403) return "unauthorized";
            if (response.code == 429 || response.code >= 500) return "retryable";
            if (response.code < 200 || response.code >= 300) return "failed";
            JsonObject value = JsonParser.parseString(response.body).getAsJsonObject();
            String status = value.get("status").getAsString();
            if ("confirmed".equals(status)) return "applied";
            return "failed".equals(status) ? "failed" : "retryable";
        } catch (Exception ignored) { return "retryable"; }
    }

    String ignore(WidgetTimerRuntimeStore.Config runtime, JsonObject command) {
        if (runtime == null || command == null) return "retryable";
        try {
            JsonObject body = new JsonObject();
            body.addProperty("habit_id", command.get("id").getAsString());
            body.addProperty("date", command.get("date").getAsString());
            body.addProperty("ignore", true);
            body.addProperty("idempotency_key", command.get("commandId").getAsString());
            Response response = transport.post(runtime.serverUrl + "/api/habits/day-ignores", runtime.authToken, body.toString());
            if (response.code == 401 || response.code == 403) return "unauthorized";
            if (response.code == 429 || response.code >= 500) return "retryable";
            if (response.code < 200 || response.code >= 300) return "rejected";
            JsonObject value = JsonParser.parseString(response.body).getAsJsonObject();
            return "confirmed".equals(value.get("status").getAsString()) && value.get("is_ignored").getAsBoolean()
                    ? "applied" : "rejected";
        } catch (Exception ignored) { return "retryable"; }
    }

    private static final class HttpTransport implements Transport {
        public Response post(String url, String token, String body) throws Exception {
            HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
            try {
                connection.setRequestMethod("POST"); connection.setConnectTimeout(3500); connection.setReadTimeout(3500);
                connection.setRequestProperty("Authorization", "Bearer " + token);
                connection.setRequestProperty("Content-Type", "application/json"); connection.setDoOutput(true);
                try (OutputStream out = connection.getOutputStream()) { out.write(body.getBytes(StandardCharsets.UTF_8)); }
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
