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
import java.util.*;

public final class HuaweiSleepAutomationService extends AccessibilityService {
    private static final String TAG="MtlSleepA11y";
    private static volatile HuaweiSleepAutomationService active;
    private volatile String step, failure;
    private volatile long stepStartedAt;
    private volatile long saveStartedAt;
    private volatile boolean saveGesturePending;
    private volatile String windowActivity; private String lastEventKey; private long lastEventAt;
    static final class Snapshot {
        final String step,failure,window;final long saveStartedAt;
        Snapshot(String step,String failure,String window,long savedFrom){this.step=step;this.failure=failure;this.window=window;saveStartedAt=savedFrom;}
    }
    static Snapshot snapshot(){HuaweiSleepAutomationService s=active;return s==null?new Snapshot(null,"accessibility_disconnected",null,0):new Snapshot(s.step,s.failure,s.windowActivity,s.saveStartedAt);}

    @Override protected void onServiceConnected() { active=this; failure=null; }
    static String send(String next) {
        HuaweiSleepAutomationService service=active;
        if(service==null) return "accessibility_disconnected";
        if(!HuaweiSleepSelectors.STEPS.contains(next)) return "invalid_step";
        if("LAUNCH_HEALTH".equals(next)){Intent i=service.getPackageManager().getLaunchIntentForPackage(HuaweiSleepSelectors.PACKAGE);if(i==null)return "huawei_not_installed";service.windowActivity=null;service.failure=null;service.saveStartedAt=0;service.setStep("OPEN_SLEEP");i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);try{service.startActivity(i);return "ok";}catch(Exception e){service.fail("launch_failed");return "launch_failed";}}
        service.failure=null; service.setStep(next); return "ok";
    }
    static void cancel(){HuaweiSleepAutomationService service=active;if(service!=null){service.step=null;service.failure="cancelled";service.windowActivity=null;}}
    static boolean openSleepPage(){
        HuaweiSleepAutomationService service=active;if(service==null)return false;
        Intent intent=new Intent(service,MainActivity.class).putExtra("route","sleep")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        try{service.startActivity(intent);return true;}catch(Exception error){Log.w(TAG,"return_to_sleep_failed",error);return false;}
    }
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
        if(known)return "ok";
        return activity.equals(home)||activity.equals(detail)||activity.equals(preview)?"wait":"unknown_window";
    }
    static String trustedActivity(String current,String candidate){if(candidate==null)return current;for(HuaweiSleepSelectors.Rule rule:HuaweiSleepSelectors.RULES.values())if(rule.activity.equals(candidate))return candidate;return candidate.contains("Login")?candidate:current;}
    static int[] gestureCenter(int left,int top,int right,int bottom){return right>left&&bottom>top?new int[]{left+(right-left)/2,top+(bottom-top)/2}:null;}
    private void saveByGesture(AccessibilityNodeInfo ignored){
        if(saveGesturePending)return;saveGesturePending=true;
        new Handler(getMainLooper()).postDelayed(()->{
            if(!"SAVE_LOCAL".equals(step)){saveGesturePending=false;return;}
            AccessibilityNodeInfo root=getRootInActiveWindow();
            if(root==null||!HuaweiSleepSelectors.allowed(root.getPackageName())){saveGesturePending=false;return;}
            List<AccessibilityNodeInfo> targets=anchoredTargets(root,HuaweiSleepSelectors.RULES.get("SAVE_LOCAL"),"SAVE_LOCAL");
            if(targets.size()!=1){saveGesturePending=false;if(targets.size()>1)fail("selector_not_unique");return;}
            performSave(targets.get(0));
        },2500);
    }
    private void performSave(AccessibilityNodeInfo target){
        Rect bounds=new Rect();target.getBoundsInScreen(bounds);int[] point=gestureCenter(bounds.left,bounds.top,bounds.right,bounds.bottom);if(point==null){saveGesturePending=false;fail("click_failed");return;}
        Log.i(TAG,"save_click=delayed_gesture");
        Path path=new Path();path.moveTo(point[0],point[1]);GestureDescription gesture=new GestureDescription.Builder().addStroke(new GestureDescription.StrokeDescription(path,0,120)).build();saveGesturePending=true;
        if(!dispatchGesture(gesture,new GestureResultCallback(){@Override public void onCompleted(GestureDescription g){saveGesturePending=false;if("SAVE_LOCAL".equals(step))setStep("SAVED");}@Override public void onCancelled(GestureDescription g){saveGesturePending=false;fail("click_failed");}},null)){saveGesturePending=false;fail("click_failed");}
    }
    private void setStep(String next){step=next;stepStartedAt=SystemClock.elapsedRealtime();if("SAVE_LOCAL".equals(next))saveStartedAt=System.currentTimeMillis();Log.i(TAG,"step="+next+" window="+windowActivity);if(!"SAVED".equals(next)){Handler h=new Handler(getMainLooper());h.postDelayed(()->pulse(next),500);h.postDelayed(()->{if(next.equals(step))fail("step_timeout");},15000);}}
    private void pulse(String expected){if(!expected.equals(step))return;Log.d(TAG,"pulse="+expected+" window="+windowActivity);AccessibilityEvent event=AccessibilityEvent.obtain(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);event.setPackageName(HuaweiSleepSelectors.PACKAGE);event.setClassName(windowActivity==null?"":windowActivity);onAccessibilityEvent(event);event.recycle();if(expected.equals(step))new Handler(getMainLooper()).postDelayed(()->pulse(expected),500);}
    private static void collectSemantic(AccessibilityNodeInfo node,String stage,List<AccessibilityNodeInfo> out){
        if(node==null)return;
        if(HuaweiSleepSelectors.matches(stage,node.getText())||HuaweiSleepSelectors.matches(stage,node.getContentDescription()))out.add(node);
        for(int i=0;i<node.getChildCount();i++)collectSemantic(node.getChild(i),stage,out);
    }
    private static AccessibilityNodeInfo actionable(AccessibilityNodeInfo evidence,HuaweiSleepSelectors.Rule rule){
        AccessibilityNodeInfo clickable=null;
        for(AccessibilityNodeInfo node=evidence;node!=null;node=node.getParent()){
            if(rule.target.equals(node.getViewIdResourceName()))return node;
            if(clickable==null&&node.isClickable())clickable=node;
        }
        return clickable;
    }
    private static List<AccessibilityNodeInfo> anchoredTargets(AccessibilityNodeInfo root,HuaweiSleepSelectors.Rule rule,String stage){
        List<AccessibilityNodeInfo> evidence=root.findAccessibilityNodeInfosByViewId(rule.evidence),matched=new ArrayList<>(),out=new ArrayList<>();
        List<String> values=new ArrayList<>();
        for(AccessibilityNodeInfo node:evidence){CharSequence value="content-desc".equals(rule.attribute)?node.getContentDescription():node.getText();values.add(value==null?"":value.toString());}
        int selected=HuaweiSleepSelectors.uniqueStage(values,stage);
        if(selected==-2)return evidence;
        if(selected<0&&"SAVE_LOCAL".equals(stage)){
            List<AccessibilityNodeInfo> explicitSave=root.findAccessibilityNodeInfosByViewId(rule.target);
            if(!explicitSave.isEmpty())return explicitSave;
        }
        if(selected>=0)matched.add(evidence.get(selected));
        if(matched.isEmpty())collectSemantic(root,stage,matched);
        if(matched.size()>1)return matched;
        for(AccessibilityNodeInfo node:matched){AccessibilityNodeInfo target=actionable(node,rule);if(target!=null)out.add(target);}
        return out;
    }
    private static String inferWindow(String step,AccessibilityNodeInfo root){
        if(root==null||!HuaweiSleepSelectors.allowed(root.getPackageName()))return null;
        String home=HuaweiSleepSelectors.RULES.get("OPEN_SLEEP").activity,detail=HuaweiSleepSelectors.RULES.get("OPEN_MORE").activity,preview=HuaweiSleepSelectors.RULES.get("SAVE_LOCAL").activity;
        if("OPEN_SLEEP".equals(step)){
            List<AccessibilityNodeInfo> cards=anchoredTargets(root,HuaweiSleepSelectors.RULES.get(step),step);
            if(cards.size()==1){
                if(HuaweiSleepSelectors.RULES.get(step).target.equals(cards.get(0).getViewIdResourceName()))return home;
                for(AccessibilityNodeInfo parent=cards.get(0);parent!=null;parent=parent.getParent())if(parent.isScrollable())return home;
            }
        }
        if(("WAIT_PREVIEW".equals(step)||"SAVE_LOCAL".equals(step))&&anchoredTargets(root,HuaweiSleepSelectors.RULES.get("SAVE_LOCAL"),"SAVE_LOCAL").size()==1)return preview;
        if(Arrays.asList("VERIFY_DAY","OPEN_MORE","CHOOSE_SHARE").contains(step)){
            if(!root.findAccessibilityNodeInfosByViewId("com.huawei.health:id/fitness_detail_time_date_tv").isEmpty())return detail;
            String semantic="CHOOSE_SHARE".equals(step)?"CHOOSE_SHARE":"OPEN_MORE";
            if(anchoredTargets(root,HuaweiSleepSelectors.RULES.get(semantic),semantic).size()==1)return detail;
        }
        return null;
    }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        if(event==null)return;long now=SystemClock.elapsedRealtime();String pkg=String.valueOf(event.getPackageName());if(event.getEventType()==AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED&&HuaweiSleepSelectors.allowed(pkg))windowActivity=trustedActivity(windowActivity,String.valueOf(event.getClassName()));AccessibilityNodeInfo root=getRootInActiveWindow();if(HuaweiSleepSelectors.allowed(pkg)){String inferred=inferWindow(step,root);if(inferred!=null)windowActivity=inferred;}String key=step+":"+event.getEventType()+":"+windowActivity;String safe=guard(step,pkg,windowActivity,key.equals(lastEventKey)&&now-lastEventAt<400);if("inactive".equals(safe)||"duplicate".equals(safe)||"wait".equals(safe))return;if(!"ok".equals(safe)){fail(safe);return;}lastEventKey=key;lastEventAt=now;
        if(root==null||step==null||!HuaweiSleepSelectors.allowed(root.getPackageName()))return;
        if("OPEN_SLEEP".equals(step)){HuaweiSleepSelectors.Rule r=HuaweiSleepSelectors.RULES.get(step);List<AccessibilityNodeInfo> target=anchoredTargets(root,r,step);if(target.isEmpty()){List<AccessibilityNodeInfo> lists=root.findAccessibilityNodeInfosByViewId("com.huawei.health:id/id_recyclerview");if(lists.size()==1&&lists.get(0).performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD))return;}String next=transition(step,windowActivity,target.size(),!target.isEmpty(),true);if("VERIFY_DAY".equals(next)){if(target.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK))setStep(next);else fail("click_failed");}else if(!"wait".equals(next))fail(next);}
        else if("VERIFY_DAY".equals(step)){List<AccessibilityNodeInfo> dates=root.findAccessibilityNodeInfosByViewId("com.huawei.health:id/fitness_detail_time_date_tv");boolean match=dates.size()==1&&HuaweiSleepSelectors.isToday(dates.get(0).getText(),new Date());String next=transition(step,windowActivity,dates.size(),true,match);if("OPEN_MORE".equals(next))setStep(next);else if(!"wait".equals(next))fail(next);}
        else if(Arrays.asList("OPEN_MORE","CHOOSE_SHARE","WAIT_PREVIEW","SAVE_LOCAL").contains(step)){String rule="WAIT_PREVIEW".equals(step)||"SAVE_LOCAL".equals(step)?"SAVE_LOCAL":step;HuaweiSleepSelectors.Rule r=HuaweiSleepSelectors.RULES.get(rule);List<AccessibilityNodeInfo> targets=anchoredTargets(root,r,rule);boolean proven=targets.size()==1;String next=transitionShare(step,windowActivity,targets.size(),proven,SystemClock.elapsedRealtime()-stepStartedAt);if("CHOOSE_SHARE".equals(next)||"WAIT_PREVIEW".equals(next)){if(targets.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK))setStep(next);else fail("click_failed");}else if("SAVE_LOCAL".equals(next)){if(!"SAVE_LOCAL".equals(step))setStep(next);saveByGesture(targets.get(0));}else if(!"wait".equals(next))fail(next);}
    }
    private void fail(String reason) { Log.w(TAG,"failed step="+step+" reason="+reason+" window="+windowActivity);failure=reason; step=null; }
    @Override public void onInterrupt() { fail("accessibility_disconnected"); active=null; }
    @Override public boolean onUnbind(Intent intent) { fail("accessibility_disconnected"); active=null; return super.onUnbind(intent); }
}
