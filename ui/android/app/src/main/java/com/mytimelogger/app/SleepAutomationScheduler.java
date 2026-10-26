package com.mytimelogger.app;

import java.util.Calendar;
import java.util.TimeZone;

final class SleepAutomationScheduler {
    static final TimeZone BEIJING = TimeZone.getTimeZone("Asia/Shanghai");
    static final long WINDOW_MS = 5L * 60L * 1000L;

    static long nextWindowStart(long nowMs) {
        Calendar next = Calendar.getInstance(BEIJING);
        next.setTimeInMillis(nowMs);
        next.set(Calendar.HOUR_OF_DAY, 8); next.set(Calendar.MINUTE, 35);
        next.set(Calendar.SECOND, 0); next.set(Calendar.MILLISECOND, 0);
        if (next.getTimeInMillis() <= nowMs) next.add(Calendar.DAY_OF_MONTH, 1);
        return next.getTimeInMillis();
    }

    static long windowEnd(long startMs) { return startMs + WINDOW_MS; }
    static boolean withinUnlockWindow(long nowMs, long startMs) {
        return startMs > 0 && nowMs >= startMs && nowMs <= windowEnd(startMs);
    }
}
