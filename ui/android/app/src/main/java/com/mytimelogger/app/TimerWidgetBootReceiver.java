package com.mytimelogger.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class TimerWidgetBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent != null && Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            TimerWidgetRenderer.refreshAll(context, "boot");
        }
    }

    static long recoveredElapsed(WidgetTimerEngine.Snapshot snapshot, long nowEpochMs) {
        if (!"countup_studying".equals(snapshot.state) || snapshot.paused) {
            return snapshot.elapsedMs;
        }
        return snapshot.elapsedMs + Math.max(0L, nowEpochMs - snapshot.capturedAtEpochMs);
    }

    static WidgetTimerEngine.Snapshot preserve(WidgetTimerEngine.Snapshot snapshot) {
        return snapshot;
    }

    static void refreshForTest() {
        TimerWidgetRenderer.refreshAll(null, "boot");
    }
}
