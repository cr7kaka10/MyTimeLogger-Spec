package com.mytimelogger.app;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.Map;

final class MorningMotivationStore {
    private static final String PREFS = "morning_motivation_v1";
    private static final String[] FALLBACK = {
        "今天先做好一件小事，行动会带你慢慢向前。", "给今天一个清晰的开始，迈出第一步就很好。",
        "把注意力放在眼前能做的事，慢慢积累力量。", "今天也可以从一个简单的选择开始照顾自己。",
        "不用赶着完成全部，先认真做完眼前的一步。", "为今天留一点耐心，每一步都算数。",
        "先开始，再调整节奏；你可以把今天过得踏实。"
    };
    static String account(Context context) {
        WidgetTimerRuntimeStore.Config config = new WidgetTimerRuntimeStore(context).read();
        return config == null ? null : config.verifiedUserId;
    }
    static boolean valid(String date, String message) {
        return date != null && date.matches("\\d{4}-\\d{2}-\\d{2}") && message != null
            && message.length() >= 12 && message.length() <= 48 && message.matches(".*[\\u4e00-\\u9fff].*")
            && !message.contains("http") && !message.contains("废物");
    }
    static boolean put(Context context, String date, String message) {
        String account = account(context);
        if (account == null || !valid(date, message)) return false;
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(account + ":" + date, message).commit();
    }
    static String today(Context context, String date) {
        String account = account(context);
        if (account == null) return null;
        String cached = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(account + ":" + date, null);
        return cached == null ? fallback(date) : cached;
    }
    static String fallback(String date) { return FALLBACK[Math.floorMod(date.hashCode(), FALLBACK.length)]; }
    static void clear(Context context, String account) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        SharedPreferences.Editor edit = prefs.edit();
        for (Map.Entry<String, ?> entry : prefs.getAll().entrySet()) if (account == null ? entry.getKey().contains(":") : entry.getKey().startsWith(account + ":")) edit.remove(entry.getKey());
        edit.apply();
    }
    private MorningMotivationStore() {}
}
