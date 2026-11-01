package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Assume;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class SleepAutomationEmulatorDeviceTest {
    @Test public void missingHuaweiIsVisibleAndCaptureButtonsDoNotClaimSuccess() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        SleepAutomationBridge.DefaultActions actions=new SleepAutomationBridge.DefaultActions(context);
        Assume.assumeTrue("missing".equals(actions.version()));
        Assume.assumeFalse(actions.accessibility());
        JSONObject status=new JSONObject(new SleepAutomationBridge(context).status());
        assertEquals("missing",status.getString("huaweiVersion"));
        assertEquals("accessibility_required",status.getString("captureBlockedReason"));
        assertFalse(actions.test());
        assertFalse(actions.oneClick());
        assertEquals("huawei_not_installed",SleepAutomationRunnerService.decide(true,true,true,true,false,true,true));
    }
}
