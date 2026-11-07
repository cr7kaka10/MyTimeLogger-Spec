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
    @Test public void jobsAreIsolatedByVerifiedAccount() {
        SleepAutomationStateStore store=new SleepAutomationStateStore();
        store.switchOwnerForTest("account-a");store.save(s("UPLOADED","2026-10-24",1));
        store.switchOwnerForTest("account-b");assertNull(store.load("2026-10-24"));assertTrue(store.history().isEmpty());
        store.save(s("MEDIA","2026-10-24",2));store.switchOwnerForTest("account-a");
        assertEquals("UPLOADED",store.load("2026-10-24").stage);
        assertEquals(1,store.history().size());
    }
    @Test public void oneClickPhaseSurvivesRestart() {
        SleepAutomationStateStore first=new SleepAutomationStateStore();
        SleepAutomationSnapshot pending=new SleepAutomationSnapshot("POLLING","2026-10-26","content://image","ocr-job",1,"ocr_pending",1,"ocr");
        first.save(pending);
        SleepAutomationStateStore restarted=new SleepAutomationStateStore();
        restarted.raw("2026-10-26",new com.google.gson.Gson().toJson(pending));
        assertEquals("ocr",restarted.load("2026-10-26").mode);
        assertEquals("ocr-job",restarted.load("2026-10-26").requestId);
    }
}
