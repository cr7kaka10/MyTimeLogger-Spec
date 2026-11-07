package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.Calendar;
import org.junit.Test;

public class EveningDiaryReminderTest {
    @Test public void onlyGeneratedFullReportWithEmptyDiaryIsReady() {
        assertEquals(EveningDiaryStore.WAITING,EveningDiaryStore.classify(1,"generated",null));
        assertEquals(EveningDiaryStore.WAITING,EveningDiaryStore.classify(2,"pending",null));
        assertEquals(EveningDiaryStore.READY,EveningDiaryStore.classify(2,"generated","  "));
        assertEquals(EveningDiaryStore.WRITTEN,EveningDiaryStore.classify(2,"generated","晚间记录"));
    }
    @Test public void checksEveryFiveMinutesAndStopsAtBeijingMidnight() {
        Calendar day=Calendar.getInstance(SleepAutomationScheduler.BEIJING);
        day.clear();day.set(2026,10,7,18,0);
        long start=day.getTimeInMillis();
        assertEquals(start,EveningDiaryReminderReceiver.nextCheck(start-60_000));
        assertEquals(start+300_000,EveningDiaryReminderReceiver.nextCheck(start));
        day.set(Calendar.HOUR_OF_DAY,23);day.set(Calendar.MINUTE,57);
        assertEquals(EveningDiaryReminderReceiver.tomorrowStart(day.getTimeInMillis()),EveningDiaryReminderReceiver.nextCheck(day.getTimeInMillis()));
    }
}
