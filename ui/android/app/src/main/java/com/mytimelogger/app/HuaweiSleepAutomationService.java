package com.mytimelogger.app;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Intent;
import android.graphics.Path;
import android.graphics.Rect;
import android.os.*;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import java.text.SimpleDateFormat;
import java.util.*;

public final class HuaweiSleepAutomationService extends AccessibilityService {
    private static final String TAG="MtlSleepA11y";
    private static volatile HuaweiSleepAutomationService active;
    private volatile String step, failure;
    private volatile long stepStartedAt;
    private volatile boolean saveGesturePending;
    private String windowActivity,lastEventKey; private long lastEventAt;

    @Override protected void onServiceConnected() { active=this; failure=null; }
    static String send(String next) {
        HuaweiSleepAutomationService service=active;
        if(service==null) return "accessibility_disconnected";
        if(!HuaweiSleepSelectors.STEPS.contains(next)) return "invalid_step";
        if("LAUNCH_HEALTH".equals(next)){Intent i=service.getPackageManager().getLaunchIntentForPackage(HuaweiSleepSelectors.PACKAGE);if(i==null)return "huawei_not_installed";i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);service.startActivity(i);next="OPEN_SLEEP";}
        service.setStep(next); service.failure=null; return "ok";
    }
    static void cancel(){HuaweiSleepAutomationService service=active;if(service!=null){service.step=null;service.failure="cancelled";service.windowActivity=null;}}
    static String transition(String step,String activity,int targets,boolean anchor,boolean today){
        if("OPEN_SLEEP".equals(step)){if(activity.contains("Login"))return "login_required";if(!HuaweiSleepSelectors.RULES.get(step).activity.equals(activity)||targets==0)return "wait";return targets==1&&anchor?"VERIFY_DAY":"selector_not_unique";}
        if("VERIFY_DAY".equals(step)){if(!HuaweiSleepSelectors.RULES.get("OPEN_MORE").activity.equals(activity)||targets==0)return "wait";return targets==1?(today?"OPEN_MORE":"date_mismatch"):"selector_not_unique";}
        return "wait";
    }
    static String transitionShare(String step,String activity,int targets,boolean evidence,long elapsed){
        if(elapsed>15000)return "step_timeout";String rule="WAIT_PREVIEW".equals(step)||"SAVE_LOCAL".equals(step)?"SAVE_LOCAL":step;HuaweiSleepSelectors.Rule r=HuaweiSleepSelectors.RULES.get(rule);
        if(r==null||!r.activity.equals(activity)||targets==0)return "wait";if(targets!=1||!evidence)return "selector_not_unique";
        if("OPEN_MORE".equals(step))return "CHOOSE_SHARE";if("CHOOSE_SHARE".equals(step))return "WAIT_PREVIEW";return "SAVE_LOCAL";
    }
    static String guard(String step,String pkg,String activity,boolean duplicate){
        if(step==null||"SAVED".equals(step))return "inactive";if("com.mytimelogger.app".equals(pkg))return "user_left";if(!HuaweiSleepSelectors.PACKAGE.equals(pkg))return "package_changed";if(duplicate)return "duplicate";if(activity==null||activity.isEmpty())return "wait";
        String home=HuaweiSleepSelectors.RULES.get("OPEN_SLEEP").activity,detail=HuaweiSleepSelectors.RULES.get("OPEN_MORE").activity,preview=HuaweiSleepSelectors.RULES.get("SAVE_LOCAL").activity;
        boolean known=("OPEN_SLEEP".equals(step)&&(activity.equals(home)||activity.contains("Login")))||"VERIFY_DAY".equals(step)&&(activity.equals(home)||activity.equals(detail))||("OPEN_MORE".equals(step)||"CHOOSE_SHARE".equals(step))&&activity.equals(detail)||"WAIT_PREVIEW".equals(step)&&(activity.equals(detail)||activity.equals(preview))||"SAVE_LOCAL".equals(step)&&activity.equals(preview);
        return known?"ok":"unknown_window";
    }
    static String trustedActivity(String current,String candidate){if(candidate==null)return current;for(HuaweiSleepSelectors.Rule rule:HuaweiSleepSelectors.RULES.values())if(rule.activity.equals(candidate))return candidate;return candidate.contains("Login")?candidate:current;}
    static int[] gestureCenter(int left,int top,int right,int bottom){return right>left&&bottom>top?new int[]{left+(right-left)/2,top+(bottom-top)/2}:null;}
    private void saveByGesture(AccessibilityNodeInfo target){
        if(saveGesturePending)return;Rect bounds=new Rect();target.getBoundsInScreen(bounds);int[] point=gestureCenter(bounds.left,bounds.top,bounds.right,bounds.bottom);if(point==null){fail("click_failed");return;}
        Path path=new Path();path.moveTo(point[0],point[1]);GestureDescription gesture=new GestureDescription.Builder().addStroke(new GestureDescription.StrokeDescription(path,0,120)).build();saveGesturePending=true;
        if(!dispatchGesture(gesture,new GestureResultCallback(){@Override public void onCompleted(GestureDescription g){saveGesturePending=false;if("SAVE_LOCAL".equals(step))setStep("SAVED");}@Override public void onCancelled(GestureDescription g){saveGesturePending=false;fail("click_failed");}},null)){saveGesturePending=false;fail("click_failed");}
    }
    private void setStep(String next){step=next;stepStartedAt=SystemClock.elapsedRealtime();Log.i(TAG,"step="+next+" window="+windowActivity);if(!"SAVED".equals(next)){Handler h=new Handler(getMainLooper());h.postDelayed(()->pulse(next),500);h.postDelayed(()->{if(next.equals(step))fail("step_timeout");},15000);}}
    private void pulse(String expected){if(!expected.equals(step))return;Log.d(TAG,"pulse="+expected+" window="+windowActivity);if(windowActivity!=null){AccessibilityEvent event=AccessibilityEvent.obtain(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);event.setPackageName(HuaweiSleepSelectors.PACKAGE);event.setClassName(windowActivity);onAccessibilityEvent(event);event.recycle();}if(expected.equals(step))new Handler(getMainLooper()).postDelayed(()->pulse(expected),500);}
    private static List<AccessibilityNodeInfo> anchoredTargets(AccessibilityNodeInfo root,HuaweiSleepSelectors.Rule rule){
        List<AccessibilityNodeInfo> evidence=root.findAccessibilityNodeInfosByViewId(rule.evidence),out=new ArrayList<>();List<String> values=new ArrayList<>();
        for(AccessibilityNodeInfo node:evidence){CharSequence value="content-desc".equals(rule.attribute)?node.getContentDescription():node.getText();values.add(String.valueOf(value));}
        int selected=HuaweiSleepSelectors.unique(values,rule.value);if(selected<0)return out;
        for(AccessibilityNodeInfo node=evidence.get(selected);node!=null;node=node.getParent())if(rule.target.equals(node.getViewIdResourceName())){out.add(node);break;}return out;
    }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        if(event==null)return;long now=SystemClock.elapsedRealtime();String pkg=String.valueOf(event.getPackageName());if(event.getEventType()==AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED&&HuaweiSleepSelectors.allowed(pkg))windowActivity=trustedActivity(windowActivity,String.valueOf(event.getClassName()));String key=step+":"+event.getEventType()+":"+windowActivity;String safe=guard(step,pkg,windowActivity,key.equals(lastEventKey)&&now-lastEventAt<400);if("inactive".equals(safe)||"duplicate".equals(safe)||"wait".equals(safe))return;if(!"ok".equals(safe)){fail(safe);return;}lastEventKey=key;lastEventAt=now;
        AccessibilityNodeInfo root=getRootInActiveWindow(); if(root==null||step==null)return;
        if("OPEN_SLEEP".equals(step)){HuaweiSleepSelectors.Rule r=HuaweiSleepSelectors.RULES.get(step);List<AccessibilityNodeInfo> target=anchoredTargets(root,r);if(target.isEmpty()){List<AccessibilityNodeInfo> lists=root.findAccessibilityNodeInfosByViewId("com.huawei.health:id/id_recyclerview");if(lists.size()==1&&lists.get(0).performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD))return;}String next=transition(step,windowActivity,target.size(),!target.isEmpty(),true);if("VERIFY_DAY".equals(next)){if(target.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK))setStep(next);else fail("click_failed");}else if(!"wait".equals(next))fail(next);}
        else if("VERIFY_DAY".equals(step)){List<AccessibilityNodeInfo> dates=root.findAccessibilityNodeInfosByViewId("com.huawei.health:id/fitness_detail_time_date_tv");SimpleDateFormat f=new SimpleDateFormat("M月d日",Locale.CHINA);f.setTimeZone(SleepAutomationScheduler.BEIJING);boolean match=dates.size()==1&&String.valueOf(dates.get(0).getText()).contains(f.format(new Date()));String next=transition(step,windowActivity,dates.size(),true,match);if("OPEN_MORE".equals(next))setStep(next);else if(!"wait".equals(next))fail(next);}
        else if(Arrays.asList("OPEN_MORE","CHOOSE_SHARE","WAIT_PREVIEW","SAVE_LOCAL").contains(step)){String rule="WAIT_PREVIEW".equals(step)||"SAVE_LOCAL".equals(step)?"SAVE_LOCAL":step;HuaweiSleepSelectors.Rule r=HuaweiSleepSelectors.RULES.get(rule);List<AccessibilityNodeInfo> targets=anchoredTargets(root,r);boolean proven=targets.size()==1;String next=transitionShare(step,windowActivity,targets.size(),proven,SystemClock.elapsedRealtime()-stepStartedAt);if("CHOOSE_SHARE".equals(next)||"WAIT_PREVIEW".equals(next)){if(targets.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK))setStep(next);else fail("click_failed");}else if("SAVE_LOCAL".equals(next)){if(!"SAVE_LOCAL".equals(step))setStep(next);saveByGesture(targets.get(0));}else if(!"wait".equals(next))fail(next);}
    }
    private void fail(String reason) { Log.w(TAG,"failed step="+step+" reason="+reason+" window="+windowActivity);failure=reason; step=null; }
    @Override public void onInterrupt() { fail("accessibility_disconnected"); active=null; }
    @Override public boolean onUnbind(Intent intent) { fail("accessibility_disconnected"); active=null; return super.onUnbind(intent); }
}
