package com.mytimelogger.app;

import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.os.Bundle;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private SqliteBridge sqliteBridge;
    private WidgetTimerBridge widgetTimerBridge;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        applySystemBars(getResources().getConfiguration());
        if (bridge == null) return;
        bridge.getWebView().setBackgroundColor(Color.WHITE);
        sqliteBridge = new SqliteBridge(this);
        bridge.getWebView().addJavascriptInterface(sqliteBridge, SqliteBridge.JAVASCRIPT_NAME);
        widgetTimerBridge = new WidgetTimerBridge(script -> bridge.getWebView().post(
            () -> bridge.getWebView().evaluateJavascript(script, null)),
            () -> TimerWidgetRenderer.refreshAll(getApplicationContext(), "app-snapshot"),
            new WidgetTimerRuntimeStore(getApplicationContext()));
        WidgetTimerBridge.attach(widgetTimerBridge);
        bridge.getWebView().addJavascriptInterface(widgetTimerBridge, WidgetTimerBridge.JAVASCRIPT_NAME);
        dispatchWidgetRoute(getIntent());
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        dispatchWidgetRoute(intent);
    }

    private void dispatchWidgetRoute(Intent intent) {
        if (bridge == null || intent == null || !"timer".equals(intent.getStringExtra("route"))) return;
        boolean focusAi = intent.getBooleanExtra("focus_ai_prompt", false);
        bridge.getWebView().post(() -> bridge.getWebView().evaluateJavascript(
                "window.__mtlPendingNavigation={route:'timer',focusAi:" + focusAi + "};" +
                "window.dispatchEvent(new CustomEvent('mtl:navigate',{detail:window.__mtlPendingNavigation}));", null));
    }

    @Override public void onDestroy() {
        if (bridge != null) bridge.getWebView().removeJavascriptInterface(SqliteBridge.JAVASCRIPT_NAME);
        if (bridge != null) bridge.getWebView().removeJavascriptInterface(WidgetTimerBridge.JAVASCRIPT_NAME);
        if (widgetTimerBridge != null) widgetTimerBridge.close();
        if (sqliteBridge != null) sqliteBridge.close();
        super.onDestroy();
    }

    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration); applySystemBars(configuration);
    }

    void applySystemBars(Configuration configuration) {
        boolean dark = (configuration.uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        getWindow().setStatusBarColor(Color.WHITE); getWindow().setNavigationBarColor(Color.WHITE);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), true);
        WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        bars.setAppearanceLightStatusBars(!dark); bars.setAppearanceLightNavigationBars(!dark);
    }
}
