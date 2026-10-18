package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.file.*;
import org.junit.Test;

public class SleepAutomationNotificationFactoryTest {
    @Test public void actionsAreBoundToExactRunAndExposeAllEntrypoints()throws Exception{
        assertTrue(SleepAutomationNotificationFactory.matchesRun("android-huawei:2026-10-01","android-huawei:2026-10-01"));
        assertFalse(SleepAutomationNotificationFactory.matchesRun("android-huawei:2026-10-01","android-huawei:2026-10-02"));
        assertFalse(SleepAutomationNotificationFactory.matchesRun("android-huawei:2026-10-01",null));
        String s=new String(Files.readAllBytes(Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationNotificationFactory.java")),"UTF-8");
        assertTrue(s.contains("停止")&&s.contains("立即重试")&&s.contains("手工上传")&&s.contains("原因："));
        assertTrue(s.contains("putExtra(SleepAutomationRunnerService.EXTRA_STAGE,\"PENDING\")"));
    }
}
