package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class SleepAutomationAlarmReceiverTest {
    @Test public void alarmIdentityIsStableAndNarrow() {
        assertEquals(840, SleepAutomationAlarmReceiver.REQUEST_CODE);
        assertEquals("com.mytimelogger.SLEEP_AUTOMATION_ALARM", SleepAutomationAlarmReceiver.ACTION);
        assertFalse(SleepAutomationAlarmReceiver.ACTION.contains("http"));
    }
    @Test public void receiverStartsRunnerWithSafeStage() throws Exception {
        String source=new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationAlarmReceiver.java")),"UTF-8");
        String manifest=new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("src/main/AndroidManifest.xml")),"UTF-8");
        assertTrue(source.contains("putExtra(SleepAutomationRunnerService.EXTRA_STAGE,\"PENDING\")"));
        assertTrue(source.contains("scheduleNext(context,now)"));
        assertTrue(manifest.contains("android.intent.action.USER_PRESENT"));
    }
    @Test public void unlockWindowAllowsOneTriggerOnlyDuringFiveMinutes() {
        long start=1_000_000L;
        assertTrue(SleepAutomationAlarmReceiver.shouldTrigger(start,start,"","2026-10-26"));
        assertTrue(SleepAutomationAlarmReceiver.shouldTrigger(start+300_000,start,"","2026-10-26"));
        assertFalse(SleepAutomationAlarmReceiver.shouldTrigger(start+300_001,start,"","2026-10-26"));
        assertFalse(SleepAutomationAlarmReceiver.shouldTrigger(start,start,"2026-10-26","2026-10-26"));
    }
}
