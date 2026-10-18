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
        assertTrue(source.contains("putExtra(SleepAutomationRunnerService.EXTRA_STAGE, \"PENDING\")"));
        assertTrue(source.contains("scheduleNext(context, System.currentTimeMillis())"));
    }
}
