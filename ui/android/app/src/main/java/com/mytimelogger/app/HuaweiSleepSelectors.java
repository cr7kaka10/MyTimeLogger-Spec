package com.mytimelogger.app;

import java.util.*;

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
    static final class Selection { final int x,y; final String selectorType; Selection(int x,int y){this.x=x;this.y=y;selectorType="coordinate_fallback";} }
    static Selection fallback(String stage,String version,int width,int height,String orientation,boolean anchor){
        if(!"OPEN_MORE".equals(stage)||!"17.0.8.300".equals(version)||width!=1220||height!=2712||!"portrait".equals(orientation)||!anchor)return null;
        return new Selection(1120,190);
    }
    static boolean allowed(CharSequence name) { return PACKAGE.contentEquals(name == null ? "" : name); }
    private HuaweiSleepSelectors() {}
}
