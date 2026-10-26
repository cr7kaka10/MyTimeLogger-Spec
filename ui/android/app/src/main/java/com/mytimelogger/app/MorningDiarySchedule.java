package com.mytimelogger.app;

import java.util.Calendar;

final class MorningDiarySchedule {
    static final long INTERVAL_MS=2L*60L*1000L;
    private static Calendar day(long now){Calendar c=Calendar.getInstance(SleepAutomationScheduler.BEIJING);c.setTimeInMillis(now);return c;}
    static long start(long now){Calendar c=day(now);c.set(Calendar.HOUR_OF_DAY,8);c.set(Calendar.MINUTE,50);c.set(Calendar.SECOND,0);c.set(Calendar.MILLISECOND,0);return c.getTimeInMillis();}
    static long end(long now){return start(now)+8L*60L*1000L;}
    static boolean inWindow(long now){return now>=start(now)&&now<=end(now);}
    static long nextInitial(long now){long start=start(now);if(now<start)return start;if(inWindow(now))return now+1000;Calendar c=day(now);c.add(Calendar.DAY_OF_MONTH,1);c.set(Calendar.HOUR_OF_DAY,8);c.set(Calendar.MINUTE,50);c.set(Calendar.SECOND,0);c.set(Calendar.MILLISECOND,0);return c.getTimeInMillis();}
    static long nextCheck(long now){if(now<start(now))return start(now);long next=now+INTERVAL_MS;if(next<=end(now))return next;Calendar c=day(now);c.add(Calendar.DAY_OF_MONTH,1);c.set(Calendar.HOUR_OF_DAY,8);c.set(Calendar.MINUTE,50);c.set(Calendar.SECOND,0);c.set(Calendar.MILLISECOND,0);return c.getTimeInMillis();}
    private MorningDiarySchedule(){}
}
