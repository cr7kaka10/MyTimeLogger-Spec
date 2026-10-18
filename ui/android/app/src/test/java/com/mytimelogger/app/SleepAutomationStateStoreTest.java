package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class SleepAutomationStateStoreTest {
    private static SleepAutomationSnapshot s(String stage, String date, long at) {
        return new SleepAutomationSnapshot(stage, date, "", "", 1, "", at);
    }

    @Test public void successIsIdempotentAndCannotGoBack() throws Exception {
        SleepAutomationStateStore store = new SleepAutomationStateStore();
        assertTrue(store.advance(s("RUNNING", "2026-09-29", 1)));
        assertTrue(store.advance(s("SUCCESS", "2026-09-29", 2)));
        assertTrue(store.advance(s("SUCCESS", "2026-09-29", 3)));
        assertFalse(store.advance(s("RUNNING", "2026-09-29", 4)));
        assertEquals("SUCCESS", store.load("2026-09-29").stage);
    }

    @Test public void corruptionIsIgnoredAndHistoryKeepsSeven() throws Exception {
        SleepAutomationStateStore store = new SleepAutomationStateStore();
        store.raw("bad", "not-json"); assertNull(store.load("bad"));
        for (int i=1;i<=9;i++) store.save(s("RUNNING", "2026-09-" + i, i));
        assertEquals(7, store.history().size());
        assertNull(store.load("2026-09-1"));
    }

    @Test public void startSourceAndRetryTimeArePersisted() {
        SleepAutomationStateStore store=new SleepAutomationStateStore();
        store.recordStartSource("main_alarm");store.setNextRetryAt(123L);
        assertEquals("main_alarm",store.lastStartSource());assertEquals(123L,store.nextRetryAt());
        store.setNextRetryAt(-1L);assertEquals(0L,store.nextRetryAt());
    }
}
