package com.mytimelogger.app;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public final class WidgetTimerCurrentState {
    public final String status, state, sessionId, categoryName, timerMode;
    public final long revision, categoryId, startedAtEpochMs, segmentStartedAtEpochMs, activeElapsedMs, durationMs, serverTimeEpochMs;
    public final int pauseCount; public final boolean active;
    private WidgetTimerCurrentState(String status, String state, String session, long revision, long categoryId, String category,
            long started, long segment, long elapsed, String mode, long duration, int pauses, long serverTime, boolean active) {
        this.status=status; this.state=state; this.sessionId=session; this.revision=revision; this.categoryId=categoryId; this.categoryName=category;
        this.startedAtEpochMs=started; this.segmentStartedAtEpochMs=segment; this.activeElapsedMs=elapsed; this.timerMode=mode;
        this.durationMs=duration; this.pauseCount=pauses; this.serverTimeEpochMs=serverTime; this.active=active;
    }
    public static WidgetTimerCurrentState parse(String raw) {
        try {
            JsonObject envelope=JsonParser.parseString(raw).getAsJsonObject(); String status=text(envelope,"status",true);
            JsonElement element=envelope.get("state");
            if ((element==null || element.isJsonNull()) && "stopped".equals(status))
                return new WidgetTimerCurrentState(status,"stopped",null,0,0,null,0,0,0,"countup",0,0,System.currentTimeMillis(),false);
            JsonObject value=element.getAsJsonObject(); String state=text(value,"state",true); boolean active=value.get("active").getAsBoolean();
            if (!("running".equals(state)||"paused".equals(state)||"stopped".equals(state)) || active != !"stopped".equals(state)) return null;
            long revision=nonNegative(value,"revision"), serverTime=time(text(value,"server_time",true));
            long category=value.has("category_id")&&!value.get("category_id").isJsonNull()?value.get("category_id").getAsLong():0;
            String categoryName=text(value,"category_name",false), session=text(value,"session_id",false), mode=text(value,"timer_mode",false);
            long started=time(text(value,"started_at",false)), segment=time(text(value,"segment_started_at",false));
            long elapsed=nonNegative(value,"active_elapsed_ms"), duration=nonNegative(value,"duration_ms"); int pauses=(int)nonNegative(value,"pause_count");
            if (serverTime<1 || (active && (category<1 || categoryName==null || session==null || started<1 || mode==null))) return null;
            return new WidgetTimerCurrentState(status,state,session,revision,category,categoryName,started,segment,elapsed,mode,duration,pauses,serverTime,active);
        } catch (Exception ignored) { return null; }
    }
    private static String text(JsonObject value,String key,boolean required) {
        JsonElement item=value.get(key); if(item==null||item.isJsonNull()) { if(required) throw new IllegalArgumentException(); return null; }
        String text=item.getAsString().trim(); if(text.isEmpty()) { if(required) throw new IllegalArgumentException(); return null; } return text;
    }
    private static long nonNegative(JsonObject value,String key) { long result=value.get(key).getAsLong(); if(result<0) throw new IllegalArgumentException(); return result; }
    private static long time(String raw) {
        if(raw==null)return 0; for(String pattern:new String[]{"yyyy-MM-dd HH:mm:ssXXX","yyyy-MM-dd'T'HH:mm:ssXXX","yyyy-MM-dd HH:mm:ss.SSSXXX","yyyy-MM-dd'T'HH:mm:ss.SSSXXX"})
            try { SimpleDateFormat format=new SimpleDateFormat(pattern,Locale.US); format.setLenient(false); Date parsed=format.parse(raw); if(parsed!=null)return parsed.getTime(); } catch(Exception ignored) { }
        return 0;
    }
}
