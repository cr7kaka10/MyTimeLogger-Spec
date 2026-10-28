package com.mytimelogger.app;

import java.util.Calendar;

final class DietCheckinReminderSchedule {
    static long next(long now) {
        Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        day.setTimeInMillis(now);
        day.set(Calendar.HOUR_OF_DAY, 22);
        day.set(Calendar.MINUTE, 50);
        day.set(Calendar.SECOND, 0);
        day.set(Calendar.MILLISECOND, 0);
        if (day.getTimeInMillis() <= now) day.add(Calendar.DAY_OF_MONTH, 1);
        return day.getTimeInMillis();
    }
    static boolean trainingDay(long now) {
        Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        day.setTimeInMillis(now);
        int weekday = day.get(Calendar.DAY_OF_WEEK);
        return weekday != Calendar.SATURDAY && weekday != Calendar.SUNDAY;
    }
    private DietCheckinReminderSchedule() {}
}
