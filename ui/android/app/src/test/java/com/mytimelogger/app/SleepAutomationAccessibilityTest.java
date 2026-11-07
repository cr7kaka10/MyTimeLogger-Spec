package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.file.*;
import org.junit.Test;

public class SleepAutomationAccessibilityTest {
    @Test public void usesExactComponentParsingForShortAndFullAndroidFormats() throws Exception {
        String source = new String(Files.readAllBytes(Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationAccessibility.java")), "UTF-8");
        assertTrue(source.contains("ComponentName.unflattenFromString"));
        assertTrue(source.contains("new ComponentName(context, HuaweiSleepAutomationService.class)"));
        assertTrue(source.contains("enabled.split(\":\")") && source.contains("expected.equals(actual)"));
        assertFalse(source.contains("contains(context.getPackageName()"));
    }
}
