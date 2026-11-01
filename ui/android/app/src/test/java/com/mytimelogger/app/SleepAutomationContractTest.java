package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class SleepAutomationContractTest {
    @Test public void preflightNamesEachActionableBlocker() {
        assertEquals("accessibility_required",SleepAutomationBridge.captureBlockReason(false,true,true,true));
        assertEquals("notifications_required",SleepAutomationBridge.captureBlockReason(true,false,true,true));
        assertEquals("media_permission_required",SleepAutomationBridge.captureBlockReason(true,true,false,true));
        assertEquals("device_locked",SleepAutomationBridge.captureBlockReason(true,true,true,false));
        assertEquals("",SleepAutomationBridge.captureBlockReason(true,true,true,true));
    }
    @Test public void reportRequiresTodaySavedProbe() {
        SleepCaptureProbeStore.Snapshot saved=new SleepCaptureProbeStore.Snapshot(
            "run-1","2026-11-01","SAVED","","content://capture",1,2,1080,2400);
        assertTrue(SleepAutomationRunnerService.isTodaySavedProbe(saved,"2026-11-01"));
        assertFalse(SleepAutomationRunnerService.isTodaySavedProbe(saved,"2026-11-02"));
        assertFalse(SleepAutomationRunnerService.isTodaySavedProbe(new SleepCaptureProbeStore.Snapshot(
            "run-2","2026-11-01","FAILED","media_unreadable","",1,0,0,0),"2026-11-01"));
    }
}
