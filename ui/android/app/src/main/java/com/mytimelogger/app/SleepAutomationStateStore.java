package com.mytimelogger.app;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.*;
import com.google.gson.Gson;

final class SleepAutomationStateStore {
    private static final String PREFIX = "android-huawei:";
    private static final String LAST_SOURCE = "meta:last-source", NEXT_RETRY = "meta:next-retry";
    private static final Gson JSON = new Gson();
    private final SharedPreferences prefs;
    private final Map<String,String> memory = new HashMap<>();
    SleepAutomationStateStore(Context context) { prefs = context.getSharedPreferences("sleep-automation", Context.MODE_PRIVATE); }
    SleepAutomationStateStore() { prefs = null; }
    String key(String sleepDate) { return PREFIX + sleepDate; }
    private String get(String key) { return prefs == null ? memory.get(key) : prefs.getString(key, null); }
    private void put(String key, String value) { if (prefs == null) memory.put(key, value); else prefs.edit().putString(key, value).commit(); }
    private void remove(String key) { if (prefs == null) memory.remove(key); else prefs.edit().remove(key).commit(); }
    void raw(String date, String value) { put(key(date), value); }
    void recordStartSource(String source) { put(LAST_SOURCE, source == null ? "unknown" : source); }
    String lastStartSource() { String value=get(LAST_SOURCE); return value==null?"":value; }
    void setNextRetryAt(long value) { put(NEXT_RETRY, Long.toString(Math.max(0,value))); }
    long nextRetryAt() { try { String value=get(NEXT_RETRY); return value==null?0:Long.parseLong(value); } catch(Exception ignored) { return 0; } }
    synchronized void save(SleepAutomationSnapshot value) { put(key(value.sleepDate), JSON.toJson(value)); trim(); }
    SleepAutomationSnapshot load(String sleepDate) { try { String raw = get(key(sleepDate)); return raw == null ? null : JSON.fromJson(raw, SleepAutomationSnapshot.class); } catch (Exception ignored) { return null; } }
    synchronized boolean advance(SleepAutomationSnapshot next) {
        SleepAutomationSnapshot old = load(next.sleepDate);
        List<String> order = Arrays.asList("PENDING","RUNNING","MEDIA","UPLOADED","POLLING","SUCCESS","FAILED");
        if (old != null && ("SUCCESS".equals(old.stage) || order.indexOf(next.stage) < order.indexOf(old.stage))) return "SUCCESS".equals(old.stage) && "SUCCESS".equals(next.stage);
        save(next); return true;
    }
    List<SleepAutomationSnapshot> history() { List<SleepAutomationSnapshot> out = new ArrayList<>(); for (String k : keys()) { SleepAutomationSnapshot s = load(k.substring(PREFIX.length())); if (s != null) out.add(s); } out.sort((a,b) -> Long.compare(b.updatedAt,a.updatedAt)); return out; }
    private Set<String> keys() { Set<String> out = new HashSet<>(); if (prefs == null) out.addAll(memory.keySet()); else for (String k : prefs.getAll().keySet()) if (k.startsWith(PREFIX)) out.add(k); return out; }
    private void trim() { List<SleepAutomationSnapshot> items = history(); for (int i=7;i<items.size();i++) remove(key(items.get(i).sleepDate)); }
}
