package com.mytimelogger.app;

import android.content.ComponentName;
import android.content.Context;
import android.provider.Settings;

final class SleepAutomationAccessibility {
    private SleepAutomationAccessibility() {}

    static boolean isEnabled(Context context) {
        String enabled = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        return contains(enabled, new ComponentName(context, HuaweiSleepAutomationService.class));
    }

    static boolean contains(String enabled, ComponentName expected) {
        if (enabled == null || enabled.trim().isEmpty()) return false;
        for (String value : enabled.split(":")) {
            ComponentName actual = ComponentName.unflattenFromString(value.trim());
            if (expected.equals(actual)) return true;
        }
        return false;
    }
}
