package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;
import org.junit.Test;

public class HuaweiSleepAutomationServiceTest {
    @Test public void scopeAndDisconnectedCommandAreStrict() {
        assertTrue(HuaweiSleepSelectors.allowed("com.huawei.health"));
        assertFalse(HuaweiSleepSelectors.allowed("com.other.app"));
        assertEquals(7, HuaweiSleepSelectors.STEPS.size());
        assertEquals("accessibility_disconnected", HuaweiSleepAutomationService.send("OPEN_SLEEP"));
    }

    @Test public void realFixtureHasExactlyOneTargetPerRule() throws Exception {
        Document d=DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(getClass().getResourceAsStream("/huawei_sleep_nodes_17_0_8_300.xml"));
        NodeList screens=d.getElementsByTagName("screen");
        for(int i=0;i<screens.getLength();i++){
            Element screen=(Element)screens.item(i); HuaweiSleepSelectors.Rule r=HuaweiSleepSelectors.RULES.get(screen.getAttribute("stage"));
            assertEquals(r.activity,screen.getAttribute("activity")); List<String> ids=new ArrayList<>(); boolean evidence=false;
            NodeList nodes=screen.getElementsByTagName("*");
            for(int n=0;n<nodes.getLength();n++){Element e=(Element)nodes.item(n);ids.add(e.getAttribute("resource-id"));if(r.evidence.equals(e.getAttribute("resource-id"))&&r.value.equals(e.getAttribute(r.attribute)))evidence=true;}
            assertTrue(evidence);
        }
    }

    @Test public void repeatedGenericIdsStillSelectOneExactEvidence() {
        assertEquals(1,HuaweiSleepSelectors.unique(Arrays.asList("运动记录","睡眠","体重管理","心脏健康"),"睡眠"));
        assertEquals(0,HuaweiSleepSelectors.unique(Arrays.asList("分享","睡眠设置","所有数据"),"分享"));
        assertEquals(0,HuaweiSleepSelectors.unique(Arrays.asList("保存","微信","朋友圈","更多"),"保存"));
        assertEquals(-2,HuaweiSleepSelectors.unique(Arrays.asList("保存","保存"),"保存"));
        assertEquals("com.huawei.health:id/hwappbarpattern_layout_ok_icon",HuaweiSleepSelectors.RULES.get("OPEN_MORE").target);
        assertEquals("com.huawei.health:id/list_popup_window_item",HuaweiSleepSelectors.RULES.get("CHOOSE_SHARE").target);
    }

    @Test public void transientWindowClassNeverReplacesTrustedActivity() {
        String home="com.huawei.health.MainActivity",detail="com.huawei.ui.main.stories.fitness.activity.coresleep.KnitSleepDetailActivity";
        assertEquals(home,HuaweiSleepAutomationService.trustedActivity(home,"android.widget.FrameLayout"));
        assertEquals(detail,HuaweiSleepAutomationService.trustedActivity(home,detail));
        assertEquals("AccountLoginActivity",HuaweiSleepAutomationService.trustedActivity(detail,"AccountLoginActivity"));
    }

    @Test public void firstHalfOnlyAdvancesOnHomeAndToday() {
        String home="com.huawei.health.MainActivity", detail="com.huawei.ui.main.stories.fitness.activity.coresleep.KnitSleepDetailActivity";
        assertEquals("VERIFY_DAY",HuaweiSleepAutomationService.transition("OPEN_SLEEP",home,1,true,true));
        assertEquals("wait",HuaweiSleepAutomationService.transition("OPEN_SLEEP",home,0,false,true));
        assertEquals("selector_not_unique",HuaweiSleepAutomationService.transition("OPEN_SLEEP",home,2,true,true));
        assertEquals("login_required",HuaweiSleepAutomationService.transition("OPEN_SLEEP","AccountLoginActivity",1,true,true));
        assertEquals("OPEN_MORE",HuaweiSleepAutomationService.transition("VERIFY_DAY",detail,1,true,true));
        assertEquals("wait",HuaweiSleepAutomationService.transition("VERIFY_DAY",detail,0,true,true));
        assertEquals("date_mismatch",HuaweiSleepAutomationService.transition("VERIFY_DAY",detail,1,true,false));
    }

    @Test public void shareHalfRequiresExactWindowEvidenceAndDeadline() {
        String detail="com.huawei.ui.main.stories.fitness.activity.coresleep.KnitSleepDetailActivity",preview="com.huawei.pluginsocialshare.activity.SharePopupActivity";
        assertEquals("CHOOSE_SHARE",HuaweiSleepAutomationService.transitionShare("OPEN_MORE",detail,1,true,100));
        assertEquals("wait",HuaweiSleepAutomationService.transitionShare("OPEN_MORE",detail,0,false,100));
        assertEquals("WAIT_PREVIEW",HuaweiSleepAutomationService.transitionShare("CHOOSE_SHARE",detail,1,true,100));
        assertEquals("SAVE_LOCAL",HuaweiSleepAutomationService.transitionShare("WAIT_PREVIEW",preview,1,true,100));
        assertEquals("selector_not_unique",HuaweiSleepAutomationService.transitionShare("OPEN_MORE",detail,2,true,100));
        assertEquals("step_timeout",HuaweiSleepAutomationService.transitionShare("OPEN_MORE",detail,1,true,15001));
    }

    @Test public void saveGestureUsesOnlyTheSelectedNodesLiveBounds() {
        assertArrayEquals(new int[]{124,2508},HuaweiSleepAutomationService.gestureCenter(34,2396,214,2621));
        assertNull(HuaweiSleepAutomationService.gestureCenter(34,2396,34,2621));
        assertNull(HuaweiSleepAutomationService.gestureCenter(214,2621,34,2396));
    }

    @Test public void unsafeWindowsAndRepeatedEventsNeverAdvance() {
        String home="com.huawei.health.MainActivity";
        assertEquals("ok",HuaweiSleepAutomationService.guard("OPEN_SLEEP","com.huawei.health",home,false));
        assertEquals("ok",HuaweiSleepAutomationService.guard("VERIFY_DAY","com.huawei.health",home,false));
        assertEquals("ok",HuaweiSleepAutomationService.guard("WAIT_PREVIEW","com.huawei.health","com.huawei.ui.main.stories.fitness.activity.coresleep.KnitSleepDetailActivity",false));
        assertEquals("duplicate",HuaweiSleepAutomationService.guard("OPEN_SLEEP","com.huawei.health",home,true));
        assertEquals("package_changed",HuaweiSleepAutomationService.guard("OPEN_SLEEP","com.android.systemui",home,false));
        assertEquals("user_left",HuaweiSleepAutomationService.guard("OPEN_SLEEP","com.mytimelogger.app",home,false));
        assertEquals("unknown_window",HuaweiSleepAutomationService.guard("OPEN_SLEEP","com.huawei.health","UnknownPopup",false));
        assertEquals("inactive",HuaweiSleepAutomationService.guard(null,"com.huawei.health",home,false));
    }

    @Test public void coordinateFallbackRequiresAllFourConstraints() {
        assertNull(HuaweiSleepSelectors.fallback("OPEN_MORE","17.0.8.301",1220,2712,"portrait",true));
        assertNull(HuaweiSleepSelectors.fallback("OPEN_MORE","17.0.8.300",1080,2400,"portrait",true));
        assertNull(HuaweiSleepSelectors.fallback("OPEN_MORE","17.0.8.300",1220,2712,"landscape",true));
        assertNull(HuaweiSleepSelectors.fallback("OPEN_MORE","17.0.8.300",1220,2712,"portrait",false));
        HuaweiSleepSelectors.Selection s=HuaweiSleepSelectors.fallback("OPEN_MORE","17.0.8.300",1220,2712,"portrait",true);
        assertNotNull(s);assertEquals("coordinate_fallback",s.selectorType);assertEquals(1120,s.x);assertEquals(190,s.y);
    }
}
