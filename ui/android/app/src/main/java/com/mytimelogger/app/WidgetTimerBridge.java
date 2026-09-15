package com.mytimelogger.app;

import android.webkit.JavascriptInterface;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

public final class WidgetTimerBridge implements AutoCloseable {
    public static final String JAVASCRIPT_NAME = "MTLTimerWidget";
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9._:-]{1,64}$");
    private static final Pattern RESULT = Pattern.compile("^(applied|requires_app|failed)$");
    interface ScriptSink { void send(String script); }
    private static volatile WidgetTimerBridge active;
    private final ScriptSink scripts;
    private final Runnable refresher;
    private final WidgetTimerRuntimeStore runtimeStore;
    private final Map<String, String> acknowledgements = new ConcurrentHashMap<>();
    private volatile boolean ready;

    WidgetTimerBridge(ScriptSink scripts) { this(scripts, () -> {}, null); }
    WidgetTimerBridge(ScriptSink scripts, Runnable refresher) { this(scripts, refresher, null); }
    WidgetTimerBridge(ScriptSink scripts, Runnable refresher, WidgetTimerRuntimeStore runtimeStore) {
        this.scripts = scripts; this.refresher = refresher; this.runtimeStore = runtimeStore;
    }
    static void attach(WidgetTimerBridge bridge) { active = bridge; }
    static WidgetTimerBridge current() { return active; }
    boolean isReady() { return ready && active == this; }

    @JavascriptInterface public void ready() { if (active == this) ready = true; }
    @JavascriptInterface public void refresh() { if (active == this) refresher.run(); }
    @JavascriptInterface public boolean configureRuntime(String json) {
        return active == this && runtimeStore != null && runtimeStore.configure(json);
    }
    @JavascriptInterface public void clearRuntime() { if (active == this && runtimeStore != null) runtimeStore.clear(); }

    void authoritativeStateChanged() {
        if (isReady()) scripts.send("window.dispatchEvent(new CustomEvent('mtl:timer-widget-snapshot-changed'))");
    }

    boolean dispatch(WidgetTimerCommand command, String categoryName) {
        if (!isReady() || command == null || categoryName == null
                || WidgetTimerCommand.isBlockedCategoryName(categoryName)) return false;
        String json = "{\"action\":\"" + command.action + "\",\"commandId\":\""
            + command.commandId + "\",\"categoryId\":" + command.categoryId
            + ",\"eventEpochMs\":" + command.eventEpochMs + "}";
        scripts.send("window.dispatchEvent(new CustomEvent('mtl:timer-widget-command',{detail:"
            + json + "}))");
        return true;
    }

    @JavascriptInterface public void ack(String commandId, String result) {
        if (commandId != null && result != null && ID.matcher(commandId).matches()
                && RESULT.matcher(result).matches()) acknowledgements.put(commandId, result);
    }

    String ackResult(String commandId) { return acknowledgements.get(commandId); }
    @Override public void close() {
        ready = false; acknowledgements.clear();
        if (active == this) active = null;
    }
}
