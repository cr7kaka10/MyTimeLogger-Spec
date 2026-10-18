package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.file.*;
import java.util.Calendar;
import org.junit.Test;

public class SleepAutomationRunnerServiceTest {
    @Test public void gateUsesSharedAccessibilityTruth() throws Exception {
        String s = new String(Files.readAllBytes(Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationRunnerService.java")), "UTF-8");
        assertTrue(s.contains("SleepAutomationAccessibility.isEnabled(this)"));
        assertFalse(s.contains("enabled.contains(getPackageName()"));
    }
    @Test public void missingBlankAndUnknownStagesNormalizeToPending(){
        assertEquals("PENDING",SleepAutomationRunnerService.normalizeStage(null));
        assertEquals("PENDING",SleepAutomationRunnerService.normalizeStage("  "));
        assertEquals("PENDING",SleepAutomationRunnerService.normalizeStage("unexpected"));
        assertEquals("FAILED:device_locked",SleepAutomationRunnerService.normalizeStage("FAILED:device_locked"));
    }
    @Test public void startSourcesAreStable(){
        assertEquals("main_alarm",SleepAutomationRunnerService.startSource(SleepAutomationAlarmReceiver.ACTION));
        assertEquals("retry_alarm",SleepAutomationRunnerService.startSource(SleepAutomationAlarmReceiver.RETRY_ACTION));
        assertEquals("notification_retry",SleepAutomationRunnerService.startSource(SleepAutomationNotificationFactory.RETRY));
        assertEquals("manual_test",SleepAutomationRunnerService.startSource(SleepAutomationRunnerService.TEST_ACTION));
    }
    @Test public void foregroundPrecedesWakeLockAndDestroyReleasesResources() throws Exception {
        String s = new String(Files.readAllBytes(Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationRunnerService.java")), "UTF-8");
        assertTrue(s.indexOf("startForeground(840") < s.indexOf("wakeLock.acquire"));
        assertTrue(s.contains("wakeLock.release()") && s.contains("worker.shutdownNow()") && s.contains("STOP_FOREGROUND_DETACH"));
        assertTrue(s.contains("states.advance(new SleepAutomationSnapshot(\"FAILED\""));
    }

    @Test public void everyMissingGateHasStableCode() {
        String[] expected={"accessibility_unavailable","notifications_denied","media_permission_limited","login_required","huawei_version_unsupported","device_locked","already_succeeded"};
        for(int missing=0;missing<expected.length;missing++) {
            boolean[] ok={true,true,true,true,true,true,true}; ok[missing]=false;
            assertTrue(expected[missing].equals(SleepAutomationRunnerService.decide(ok)));
        }
        assertTrue("ok".equals(SleepAutomationRunnerService.decide(true,true,true,true,true,true,true)));
    }

    @Test public void persistedMediaSkipsCaptureAndOnlyOkCanContinue(){
        assertTrue(SleepAutomationRunnerService.needsCapture(null));
        SleepAutomationSnapshot s=new SleepAutomationSnapshot("MEDIA","2026-09-29","content://image/1","",1,"",1);
        assertTrue(!SleepAutomationRunnerService.needsCapture(s));
        assertTrue(SleepAutomationRunnerService.acceptsMedia("ok"));
        assertTrue(!SleepAutomationRunnerService.acceptsMedia("media_not_found"));
    }

    @Test public void requestIdAlwaysChoosesPollInsteadOfUpload(){
        SleepAutomationSnapshot media=new SleepAutomationSnapshot("MEDIA","2026-10-01","content://1","",1,"",1);
        SleepAutomationSnapshot uploaded=new SleepAutomationSnapshot("UPLOADED","2026-10-01","content://1","req-1",1,"",1);
        assertTrue("upload".equals(SleepAutomationRunnerService.nextNetworkAction(media)));
        assertTrue("poll".equals(SleepAutomationRunnerService.nextNetworkAction(uploaded)));
        assertTrue("capture".equals(SleepAutomationRunnerService.nextNetworkAction(null)));
    }
    @Test public void apiStatesSeparateSuccessPermanentAndRecoverable(){
        assertTrue("SUCCESS".equals(SleepAutomationRunnerService.outcome("done",true)));
        assertTrue("SUCCESS".equals(SleepAutomationRunnerService.outcome("reused",true)));
        assertTrue("FAILED".equals(SleepAutomationRunnerService.outcome("done",false)));
        assertTrue("FAILED".equals(SleepAutomationRunnerService.outcome("error",false)));
        assertTrue("POLLING".equals(SleepAutomationRunnerService.outcome("network_error",false)));
        assertTrue("POLLING".equals(SleepAutomationRunnerService.outcome("running",false)));
        SleepAutomationStateStore store=new SleepAutomationStateStore();store.save(new SleepAutomationSnapshot("SUCCESS","2026-10-01","","",1,"",1));
        assertTrue(store.advance(new SleepAutomationSnapshot("RUNNING","2026-10-02","","",1,"",2)));
    }
    private static long at(int h,int m){Calendar c=Calendar.getInstance(SleepAutomationScheduler.BEIJING);c.clear();c.set(2026,Calendar.OCTOBER,1,h,m);return c.getTimeInMillis();}
    @Test public void retrySlotsAreBoundedAndPermanentErrorsStop(){
        assertEquals(at(8,50),SleepAutomationRunnerService.nextRetry(at(8,40),"device_locked"));
        assertEquals(at(9,10),SleepAutomationRunnerService.nextRetry(at(8,50),"media_not_found"));
        assertEquals(at(10,10),SleepAutomationRunnerService.nextRetry(at(9,40),"network_error"));
        assertEquals(-1,SleepAutomationRunnerService.nextRetry(at(10,30),"network_error"));
        assertEquals(-1,SleepAutomationRunnerService.nextRetry(at(8,40),"unauthorized"));
    }
}
