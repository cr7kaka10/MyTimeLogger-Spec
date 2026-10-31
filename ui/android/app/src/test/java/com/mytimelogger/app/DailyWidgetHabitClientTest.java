package com.mytimelogger.app;

import static org.junit.Assert.*;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.Test;

public class DailyWidgetHabitClientTest {
    private final WidgetTimerRuntimeStore.Config runtime =
            new WidgetTimerRuntimeStore.Config("https://example.test", "token", "device", "user", 1);
    private static JsonObject command(String action) {
        JsonObject command = new JsonObject();
        command.addProperty("id", "habit-1"); command.addProperty("date", "2026-10-21");
        command.addProperty("action", action); command.addProperty("commandId", "daily-fixed");
        return command;
    }
    @Test public void completeAndFailUseSameStableIdWithDistinctStatus() {
        String[] bodies = new String[2]; int[] call = {0};
        DailyWidgetHabitClient client = new DailyWidgetHabitClient((url, token, body) -> {
            assertEquals("https://example.test/api/habits/checkin-commands", url);
            assertEquals("token", token); bodies[call[0]++] = body;
            return new DailyWidgetHabitClient.Response(200, "{\"status\":\"confirmed\"}");
        });
        assertEquals("applied", client.apply(runtime, command("complete")));
        assertEquals("applied", client.apply(runtime, command("fail")));
        assertEquals(2, JsonParser.parseString(bodies[0]).getAsJsonObject().get("desired_status").getAsInt());
        assertEquals(1, JsonParser.parseString(bodies[1]).getAsJsonObject().get("desired_status").getAsInt());
        for (String body : bodies) assertEquals("daily-fixed",
                JsonParser.parseString(body).getAsJsonObject().get("idempotency_key").getAsString());
    }
    @Test public void unknownNetworkResultKeepsCommandRetryable() {
        DailyWidgetHabitClient client = new DailyWidgetHabitClient((url, token, body) -> {
            throw new java.io.IOException("timeout");
        });
        JsonObject fixed = command("fail");
        assertEquals("retryable", client.apply(runtime, fixed));
        assertEquals("retryable", client.apply(runtime, fixed));
        assertEquals("daily-fixed", fixed.get("commandId").getAsString());
        assertEquals("unauthorized", new DailyWidgetHabitClient((url, token, body) ->
                new DailyWidgetHabitClient.Response(401, "{}")).apply(runtime, fixed));
    }
    @Test public void ignoreUsesStableCommandAndRequiresConfirmedIgnoredState() {
        JsonObject command = command("ignore");
        DailyWidgetHabitClient client = new DailyWidgetHabitClient((url, token, body) -> {
            assertEquals("https://example.test/api/habits/day-ignores", url);
            assertEquals("token", token);
            JsonObject sent = JsonParser.parseString(body).getAsJsonObject();
            assertEquals("habit-1", sent.get("habit_id").getAsString());
            assertEquals("daily-fixed", sent.get("idempotency_key").getAsString());
            assertTrue(sent.get("ignore").getAsBoolean());
            return new DailyWidgetHabitClient.Response(200, "{\"status\":\"confirmed\",\"is_ignored\":true}");
        });
        assertEquals("applied", client.ignore(runtime, command));
        assertEquals("applied", client.ignore(runtime, command));
        assertEquals("retryable", new DailyWidgetHabitClient((url, token, body) ->
                new DailyWidgetHabitClient.Response(503, "")).ignore(runtime, command));
        assertEquals("rejected", new DailyWidgetHabitClient((url, token, body) ->
                new DailyWidgetHabitClient.Response(409, "{}")).ignore(runtime, command));
    }
}
