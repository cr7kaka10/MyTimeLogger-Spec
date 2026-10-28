package com.mytimelogger.app;

import java.util.Calendar;

final class MealDeadlineSchedule {
    static final String[] RULES = {"breakfast_on_time", "lunch_on_time", "dinner_on_time"};
    static final String[] NAMES = {"早餐", "午餐", "晚餐"};
    private static final int[] HOURS = {8, 13, 19};
    private static final int[] MINUTES = {30, 31, 1};
    static long next(long now, int meal) {
        Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        day.setTimeInMillis(now); day.set(Calendar.HOUR_OF_DAY, HOURS[meal]);
        day.set(Calendar.MINUTE, MINUTES[meal]); day.set(Calendar.SECOND, 0); day.set(Calendar.MILLISECOND, 0);
        if (day.getTimeInMillis() <= now) day.add(Calendar.DAY_OF_MONTH, 1);
        return day.getTimeInMillis();
    }
    static boolean isDue(long now, int meal) {
        Calendar day = Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        day.setTimeInMillis(now); day.set(Calendar.HOUR_OF_DAY, HOURS[meal]);
        day.set(Calendar.MINUTE, MINUTES[meal]); day.set(Calendar.SECOND, 0); day.set(Calendar.MILLISECOND, 0);
        return now >= day.getTimeInMillis() && now < day.getTimeInMillis() + 120_000;
    }
    private MealDeadlineSchedule() {}
}
