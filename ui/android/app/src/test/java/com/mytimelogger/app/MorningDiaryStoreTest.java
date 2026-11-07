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
        assertEquals(start+MorningDiarySchedule.INTERVAL_MS,MorningDiarySchedule.nextInitial(start+30_000));
        assertEquals(start+MorningDiarySchedule.INTERVAL_MS*4,MorningDiarySchedule.nextCheck(start+MorningDiarySchedule.INTERVAL_MS*3+30_000));
        assertFalse(MorningDiarySchedule.inWindow(start+MorningDiarySchedule.INTERVAL_MS*5));
        assertEquals(start+MorningDiarySchedule.INTERVAL_MS*4,MorningDiarySchedule.nextCheck(start+MorningDiarySchedule.INTERVAL_MS*3));
        java.util.Calendar tomorrow=(java.util.Calendar)c.clone();tomorrow.add(java.util.Calendar.DAY_OF_MONTH,1);tomorrow.set(java.util.Calendar.HOUR_OF_DAY,8);tomorrow.set(java.util.Calendar.MINUTE,50);tomorrow.set(java.util.Calendar.SECOND,0);tomorrow.set(java.util.Calendar.MILLISECOND,0);
        assertEquals(tomorrow.getTimeInMillis(),MorningDiarySchedule.nextCheck(start+8L*60L*1000L));
    }
    @Test public void stopsReminderAfterSavedDiaryAndRestoresAcrossLifecycle(){
        assertFalse(MorningDiaryReminderReceiver.shouldRemind(MorningDiaryStore.WRITTEN));
        assertTrue(MorningDiaryReminderReceiver.shouldRemind(MorningDiaryStore.MISSING));
        assertTrue(MorningDiaryReminderReceiver.shouldRemind(MorningDiaryStore.UNKNOWN));
        assertEquals(850,MorningDiaryReminderReceiver.NOTIFICATION);
        try{
            String main=new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("src/main/java/com/mytimelogger/app/MainActivity.java")),"UTF-8");
            String boot=new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationRescheduleReceiver.java")),"UTF-8");
            String manifest=new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("src/main/AndroidManifest.xml")),"UTF-8");
            assertTrue(main.contains("MorningDiaryReminderReceiver.scheduleInitial"));assertTrue(boot.contains("MorningDiaryReminderReceiver.scheduleInitial"));assertTrue(manifest.contains(".MorningDiaryReminderReceiver"));
        }catch(java.io.IOException error){throw new AssertionError(error);}
    }
}
