package com.mytimelogger.app;

import static org.junit.Assert.*;
import com.google.gson.JsonParser;
import org.junit.Test;

public class DailyWidgetJournalClientTest {
    private final WidgetTimerRuntimeStore.Config runtime =
            new WidgetTimerRuntimeStore.Config("https://example.test", "token", "device", "user", 1);

    @Test public void onlyActiveLocalHabitsWithPreferencePrompt() {
        DailyWidgetJournalClient local = new DailyWidgetJournalClient((method, url, token, body) -> {
            assertEquals("GET", method); assertEquals("https://example.test/api/habits", url);
            assertEquals("token", token);
            return new DailyWidgetJournalClient.Response(200,
                    "{\"habits\":[{\"id\":\"h1\",\"source\":\"local\",\"is_active\":0,\"journal_prompt_enabled\":1}]}");
        });
        assertEquals(Boolean.TRUE, local.promptEnabled(runtime, "h1"));
        assertNull(local.promptEnabled(runtime, "missing"));
        DailyWidgetJournalClient disabled = new DailyWidgetJournalClient((method, url, token, body) ->
                new DailyWidgetJournalClient.Response(200,
                        "{\"habits\":[{\"id\":\"h1\",\"source\":\"local\",\"is_active\":0,\"journal_prompt_enabled\":0}]}"));
        assertEquals(Boolean.FALSE, disabled.promptEnabled(runtime, "h1"));
        DailyWidgetJournalClient system = new DailyWidgetJournalClient((method, url, token, body) ->
                new DailyWidgetJournalClient.Response(200,
                        "{\"habits\":[{\"id\":\"h1\",\"source\":\"v5-diet\",\"is_active\":0,\"journal_prompt_enabled\":1}]}") );
        assertEquals(Boolean.FALSE, system.promptEnabled(runtime, "h1"));
    }

    @Test public void journalAndDisableUseAuthenticatedExistingEndpoints() {
        int[] calls = {0};
        DailyWidgetJournalClient client = new DailyWidgetJournalClient((method, url, token, body) -> {
            assertEquals("PUT", method); assertEquals("token", token);
            if (calls[0]++ == 0) {
                assertEquals("https://example.test/api/habits/h1/checkins/2026-11-02/journal", url);
                assertEquals("🙂 做得好", JsonParser.parseString(body).getAsJsonObject().get("note").getAsString());
            } else {
                assertEquals("https://example.test/api/habits/h1/journal-prompt", url);
                assertFalse(JsonParser.parseString(body).getAsJsonObject().get("enabled").getAsBoolean());
            }
            return new DailyWidgetJournalClient.Response(200, "{}");
        });
        assertTrue(client.save(runtime, "h1", "2026-11-02", "🙂 做得好"));
        assertTrue(client.disable(runtime, "h1")); assertEquals(2, calls[0]);
    }

    @Test public void networkFailureNeverClaimsJournalSaved() {
        DailyWidgetJournalClient client = new DailyWidgetJournalClient((method, url, token, body) -> {
            throw new java.io.IOException("offline");
        });
        assertNull(client.promptEnabled(runtime, "h1"));
        assertFalse(client.save(runtime, "h1", "2026-11-02", "🙂"));
        assertFalse(client.disable(runtime, "h1"));
        assertFalse(client.save(runtime, "../bad", "2026-11-02", "x"));
    }
}
