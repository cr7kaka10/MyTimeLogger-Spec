package com.mytimelogger.app;
import static org.junit.Assert.*;
import android.content.*;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.lang.reflect.Method;
import java.security.KeyStore;
import org.junit.Test;
import org.junit.runner.RunWith;
@RunWith(AndroidJUnit4.class)
public class SecureStorageLifecycleTest {
    private static final String ALIAS = "capacitor-storage_mtl.credential.lifecycle_probe";
    private static final String PREFS = "WSSecureStorageSharedPreferences", SECRET = "lifecycle-secret-value";
    @Test public void phaseContract() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String phase = InstrumentationRegistry.getArguments().getString("phase", "seed");
        if ("seed".equals(phase)) seedWithRealPlugin();
        boolean expected = !"fresh_install".equals(phase);
        KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore"); keyStore.load(null);
        String ciphertext = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(ALIAS, null);
        assertEquals(expected, keyStore.containsAlias(ALIAS)); assertEquals(expected, ciphertext != null);
        if (ciphertext != null) assertFalse(ciphertext.contains(SECRET));
    }
    private static void seedWithRealPlugin() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                try {
                    Object plugin = activity.getBridge().getPlugin("SecureStorage").getInstance();
                    Method store = plugin.getClass().getDeclaredMethod("storeDataInKeyStore", String.class, String.class);
                    store.setAccessible(true); store.invoke(plugin, ALIAS, SECRET);
                } catch (Exception error) { throw new AssertionError(error); }
            });
        }
    }
}
