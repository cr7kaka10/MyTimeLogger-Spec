package com.mytimelogger.app;

import static org.junit.Assert.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.Test;

public class AndroidLaunchThemeContractTest {
    @Test public void launchThemeReturnsToTheNormalAppTheme() throws Exception {
        String styles = new String(Files.readAllBytes(Paths.get("src/main/res/values/styles.xml")),
                StandardCharsets.UTF_8);
        String manifest = new String(Files.readAllBytes(Paths.get("src/main/AndroidManifest.xml")),
                StandardCharsets.UTF_8);
        String activity = new String(Files.readAllBytes(Paths.get(
                "src/main/java/com/mytimelogger/app/MainActivity.java")), StandardCharsets.UTF_8);
        assertTrue(manifest.contains("android:theme=\"@style/AppTheme.NoActionBar\""));
        assertTrue(styles.contains("<style name=\"AppTheme.NoActionBar\" parent=\"Theme.AppCompat.DayNight.NoActionBar\""));
        assertTrue(styles.contains("android:windowBackground\">@android:color/white"));
        assertTrue(styles.contains("android:windowIsTranslucent\">false"));
        assertTrue(styles.contains("android:windowDisablePreview\">true"));
        assertTrue(styles.contains("android:windowAnimationStyle\">@null"));
        assertTrue(!styles.contains("Theme.SplashScreen"));
        assertTrue(activity.contains("bridge.getWebView().setBackgroundColor(Color.WHITE);"));
    }
}
