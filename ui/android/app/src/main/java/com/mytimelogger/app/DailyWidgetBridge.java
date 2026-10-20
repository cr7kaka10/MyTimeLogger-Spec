package com.mytimelogger.app;

import android.content.Context;
import android.webkit.JavascriptInterface;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.Map;

public final class DailyWidgetBridge implements AutoCloseable {
    public static final String JAVASCRIPT_NAME = "MTLDailyWidget";
    interface ScriptSink { void send(String script); }
    private static volatile DailyWidgetBridge active;
    private final Context context;
    private final ScriptSink scripts;
    private volatile boolean ready;
    private volatile boolean foreground;
    DailyWidgetBridge(Context context, ScriptSink scripts) {
        this.context = context.getApplicationContext(); this.scripts = scripts;
    }
    static void attach(DailyWidgetBridge bridge) { active = bridge; }
    static DailyWidgetBridge current() { return active; }
    Context contextForClear() { return context; }
    boolean isReady() { return active == this && ready && foreground; }
    void setForeground(boolean value) {
        foreground = value;
        if (value && ready) dispatchPending();
    }
    @JavascriptInterface public void ready() {
        if (active != this) return;
        ready = true;
        dispatchPending();
    }
    private void dispatchPending() {
        if (!isReady()) return;
        if (new DailyWidgetStore(context).snapshot() == null) return;
        ArrayList<Map.Entry<String, JsonElement>> pending = new ArrayList<>(new DailyWidgetStore(context).pending().entrySet());
        if (!pending.isEmpty()) scripts.send("window.dispatchEvent(new CustomEvent('mtl:navigate',{detail:{route:'checklist'}}))");
        for (Map.Entry<String, JsonElement> item : pending)
            dispatch(item.getValue().getAsJsonObject());
    }
    @JavascriptInterface public void pause() { if (active == this) ready = false; }
    @JavascriptInterface public boolean publish(String value) {
        if (active != this) return false;
        boolean saved = new DailyWidgetStore(context).publish(value);
        if (saved) {
            DailyWidgetProvider.refresh(context);
            dispatchPending();
        }
        return saved;
    }
    @JavascriptInterface public void refresh() {
        if (active == this) DailyWidgetProvider.refresh(context);
    }
    @JavascriptInterface public void ack(String commandId, String result) {
        if (active != this || commandId == null || !commandId.matches("daily-[0-9a-fA-F-]{36}")
                || !("applied".equals(result) || "pending_sync".equals(result) || "failed".equals(result))) return;
        new DailyWidgetStore(context).ack(commandId, result);
        DailyWidgetProvider.refresh(context);
        if (!"applied".equals(result)) new Handler(Looper.getMainLooper()).post(() -> Toast.makeText(context,
                "pending_sync".equals(result) ? "已完成，等待同步" : "完成失败，请检查网络后重试", Toast.LENGTH_SHORT).show());
    }
    void dispatch(JsonObject command) {
        if (!isReady() || command == null) return;
        JsonObject snapshot = new DailyWidgetStore(context).snapshot();
        try {
            if (snapshot == null || !DailyWidgetStore.today().equals(command.get("date").getAsString())
                    || !snapshot.get("userId").getAsString().equals(command.get("userId").getAsString())
                    || snapshot.get("generation").getAsLong() != command.get("generation").getAsLong()) return;
            scripts.send("window.dispatchEvent(new CustomEvent('mtl:daily-widget-command',{detail:"
                    + command.toString() + "}))");
        } catch (RuntimeException ignored) { }
    }
    static void clear(Context context) {
        new DailyWidgetStore(context).clear();
        DailyWidgetProvider.refresh(context);
    }
    @Override public void close() { ready = false; foreground = false; if (active == this) active = null; }
}
