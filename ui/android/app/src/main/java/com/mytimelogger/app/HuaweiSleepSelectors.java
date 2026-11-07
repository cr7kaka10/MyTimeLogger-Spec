package com.mytimelogger.app;

import java.util.*;
import java.text.SimpleDateFormat;

final class HuaweiSleepSelectors {
    static final String PACKAGE="com.huawei.health";
    static final List<String> STEPS=Arrays.asList("LAUNCH_HEALTH","OPEN_SLEEP","VERIFY_DAY","OPEN_MORE","CHOOSE_SHARE","WAIT_PREVIEW","SAVE_LOCAL");
    static final class Rule {
        final String activity,target,evidence,attribute,value;
        Rule(String... v){activity=v[0];target=v[1];evidence=v[2];attribute=v[3];value=v[4];}
    }
    static final Map<String,Rule> RULES=new LinkedHashMap<>();
    static {
        RULES.put("OPEN_SLEEP",new Rule("com.huawei.health.MainActivity","com.huawei.health:id/function_set_card_view","com.huawei.health:id/function_set_items_title","text","睡眠"));
        RULES.put("OPEN_MORE",new Rule("com.huawei.ui.main.stories.fitness.activity.coresleep.KnitSleepDetailActivity","com.huawei.health:id/hwappbarpattern_layout_ok_icon","com.huawei.health:id/hwappbarpattern_ok_icon","content-desc","更多选项"));
        RULES.put("CHOOSE_SHARE",new Rule("com.huawei.ui.main.stories.fitness.activity.coresleep.KnitSleepDetailActivity","com.huawei.health:id/list_popup_window_item","com.huawei.health:id/list_popup_window_item_text","text","分享"));
        RULES.put("SAVE_LOCAL",new Rule("com.huawei.pluginsocialshare.activity.SharePopupActivity","com.huawei.health:id/share_save_to_local_layout","com.huawei.health:id/share_tv","text","保存"));
    }
    static int unique(List<String> ids,String target){int found=-1;for(int i=0;i<ids.size();i++)if(target.equals(ids.get(i))){if(found>=0)return -2;found=i;}return found;}
    static boolean matches(String stage, CharSequence value){
        if(value==null)return false;
        String text=value.toString().trim().toLowerCase(Locale.ROOT);
        switch(stage){
            case "OPEN_SLEEP": return "睡眠".equals(text)||"sleep".equals(text);
            case "OPEN_MORE": return "更多选项".equals(text)||"more items".equals(text)||"more options".equals(text);
            case "CHOOSE_SHARE": return "分享".equals(text)||"share".equals(text);
            case "SAVE_LOCAL": return "保存".equals(text)||"save".equals(text);
            default: return false;
        }
    }
    static int uniqueStage(List<String> values,String stage){
        int found=-1;
        for(int i=0;i<values.size();i++)if(matches(stage,values.get(i))){if(found>=0)return -2;found=i;}
        return found;
    }
    static boolean isToday(CharSequence label,Date now){
        if(label==null)return false;
        String shown=label.toString().trim();
        for(String pattern:new String[]{"M月d日","EEE, MMM d","MMM d","d MMM"}){
            SimpleDateFormat format=new SimpleDateFormat(pattern,pattern.contains("月")?Locale.CHINA:Locale.ENGLISH);
            format.setTimeZone(SleepAutomationScheduler.BEIJING);
            if(pattern.contains("月")?shown.contains(format.format(now)):shown.equalsIgnoreCase(format.format(now)))return true;
        }
        return false;
    }
    static boolean allowed(CharSequence name) { return PACKAGE.contentEquals(name == null ? "" : name); }
    private HuaweiSleepSelectors() {}
}
