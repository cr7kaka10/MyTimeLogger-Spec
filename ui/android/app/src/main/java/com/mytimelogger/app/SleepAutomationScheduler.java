package com.mytimelogger.app;

import java.util.Calendar;
import java.util.TimeZone;

final class SleepAutomationScheduler {
    static final TimeZone BEIJING = TimeZone.getTimeZone("Asia/Shanghai");
    static final long WINDOW_MS = 20L * 60L * 1000L;

    static long next840(long nowMs) {
        Calendar next = Calendar.getInstance(BEIJING);
        next.setTimeInMillis(nowMs);
        next.set(Calendar.HOUR_OF_DAY, 8); next.set(Calendar.MINUTE, 40);
        next.set(Calendar.SECOND, 0); next.set(Calendar.MILLISECOND, 0);
        if (next.getTimeInMillis() <= nowMs) next.add(Calendar.DAY_OF_MONTH, 1);
        return next.getTimeInMillis();
    }

    static long windowEnd(long startMs) { return startMs + WINDOW_MS; }
}
