package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class MorningDiaryStoreTest {
    @Test public void classifiesOnlyNonBlankDiaryAsWritten(){
        assertEquals(MorningDiaryStore.WRITTEN,MorningDiaryStore.classify("晨间记录"));
        assertEquals(MorningDiaryStore.MISSING,MorningDiaryStore.classify("  "));
        assertEquals(MorningDiaryStore.MISSING,MorningDiaryStore.classify(null));
    }
    @Test public void schedulesChecksInsideBeijingWindowAndStopsAtEnd(){
        java.util.Calendar c=java.util.Calendar.getInstance(SleepAutomationScheduler.BEIJING);c.clear();c.set(2026,9,26,8,50);
        long start=c.getTimeInMillis();assertTrue(MorningDiarySchedule.inWindow(start));
        assertEquals(start+MorningDiarySchedule.INTERVAL_MS,MorningDiarySchedule.nextCheck(start));
        assertFalse(MorningDiarySchedule.inWindow(start+MorningDiarySchedule.INTERVAL_MS*5));
    }
}
