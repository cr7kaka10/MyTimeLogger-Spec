package com.mytimelogger.app;
import static org.junit.Assert.*;
import android.content.res.Configuration;
import android.graphics.Color;
import androidx.core.view.*;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
@RunWith(AndroidJUnit4.class)
public class SystemBarsTest {
    @Test public void lightDarkGestureBarsAndRotationStayAligned() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(activity.getWindow(), activity.getWindow().getDecorView());
                Configuration light = new Configuration(activity.getResources().getConfiguration());
                light.uiMode = (light.uiMode & ~Configuration.UI_MODE_NIGHT_MASK) | Configuration.UI_MODE_NIGHT_NO;
                activity.applySystemBars(light);
                assertTrue(bars.isAppearanceLightStatusBars()); assertTrue(bars.isAppearanceLightNavigationBars());
                Configuration dark = new Configuration(light); dark.uiMode = (dark.uiMode & ~Configuration.UI_MODE_NIGHT_MASK) | Configuration.UI_MODE_NIGHT_YES;
                dark.orientation = Configuration.ORIENTATION_LANDSCAPE; activity.onConfigurationChanged(dark);
                assertFalse(bars.isAppearanceLightStatusBars()); assertFalse(bars.isAppearanceLightNavigationBars());
                assertEquals(Color.TRANSPARENT, activity.getWindow().getStatusBarColor());
                assertEquals(Color.TRANSPARENT, activity.getWindow().getNavigationBarColor());
            });
        }
    }
}
