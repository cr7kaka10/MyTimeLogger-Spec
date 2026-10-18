package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.lang.reflect.Method;
import java.util.*;
import org.junit.Test;

public class SleepAutomationBridgeTest {
    @Test public void nativeStatusUsesSharedAccessibilityTruth() throws Exception {String s=new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationBridge.java")),"UTF-8");assertTrue(s.contains("SleepAutomationAccessibility.isEnabled(c)"));assertFalse(s.contains("v.contains(c.getPackageName()"));}
    @Test public void exposesOnlyNarrowJavascriptSurface() {
        Set<String> exposed=new HashSet<>(); for(Method m:SleepAutomationBridge.class.getDeclaredMethods()) if(m.getAnnotation(android.webkit.JavascriptInterface.class)!=null) exposed.add(m.getName());
        assertEquals(new HashSet<>(Arrays.asList("status","enable","disable","test","cancel","configure","authorize","clearConfiguration")),exposed);
        assertFalse(exposed.contains("intent")); assertFalse(exposed.contains("tap")); assertFalse(exposed.contains("packageName"));
    }
    @Test public void forwardsEveryNarrowAction(){final StringBuilder calls=new StringBuilder();SleepAutomationBridge bridge=new SleepAutomationBridge(new SleepAutomationBridge.Actions(){public String status(){calls.append("s");return "{}";}public boolean enable(){calls.append("e");return true;}public void disable(){calls.append("d");}public boolean test(){calls.append("t");return true;}public void cancel(){calls.append("c");}public boolean configure(String u,String t){calls.append("f");return "u".equals(u)&&"t".equals(t);}public boolean authorize(String p){calls.append("a");return "media".equals(p);}public void clearConfiguration(){calls.append("x");}});assertEquals("{}",bridge.status());assertTrue(bridge.enable());bridge.disable();assertTrue(bridge.test());bridge.cancel();assertTrue(bridge.configure("u","t"));assertTrue(bridge.authorize("media"));bridge.clearConfiguration();assertEquals("sedtcfax",calls.toString());}
    @Test public void nativeStatusExposesBuildScheduleAndSource() throws Exception {String s=new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationBridge.java")),"UTF-8");assertTrue(s.contains("\"buildId\"")&&s.contains("\"nextRunAt\"")&&s.contains("\"nextRetryAt\"")&&s.contains("\"lastStartSource\""));}
    @Test public void debugOnlyAcceptsPublicCleartextTestServer(){assertTrue(SleepAutomationBridge.serverUrlAllowed("http://223.109.142.12:8000",true));assertFalse(SleepAutomationBridge.serverUrlAllowed("http://223.109.142.12:8000",false));assertTrue(SleepAutomationBridge.serverUrlAllowed("https://example.test",false));assertTrue(SleepAutomationBridge.serverUrlAllowed("http://127.0.0.1:8000",false));assertTrue(SleepAutomationBridge.serverUrlAllowed("http://192.168.1.2:8000",false));assertFalse(SleepAutomationBridge.serverUrlAllowed("ftp://example.test",true));assertFalse(SleepAutomationBridge.serverUrlAllowed("not-a-url",true));}
}
