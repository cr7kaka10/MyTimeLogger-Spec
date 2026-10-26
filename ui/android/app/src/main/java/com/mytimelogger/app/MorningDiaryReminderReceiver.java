package com.mytimelogger.app;

import android.app.*;
import android.content.*;
import android.os.Build;
import androidx.core.app.NotificationManagerCompat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public final class MorningDiaryReminderReceiver extends BroadcastReceiver {
    static final String ACTION="com.mytimelogger.MORNING_DIARY_CHECK";
    static final int REQUEST=850, NOTIFICATION=850;
    static PendingIntent pending(Context c){Intent i=new Intent(c,MorningDiaryReminderReceiver.class).setAction(ACTION);return PendingIntent.getBroadcast(c,REQUEST,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
    static void scheduleInitial(Context c,long now){scheduleAt(c,MorningDiarySchedule.nextInitial(now));}
    static void scheduleAt(Context c,long at){AlarmManager a=(AlarmManager)c.getSystemService(Context.ALARM_SERVICE);PendingIntent p=pending(c);if(Build.VERSION.SDK_INT<31||a.canScheduleExactAlarms())a.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,at,p);else a.setWindow(AlarmManager.RTC_WAKEUP,at,60_000,p);}
    static String today(long now){SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd",Locale.ROOT);f.setTimeZone(SleepAutomationScheduler.BEIJING);return f.format(new Date(now));}
    @Override public void onReceive(Context c,Intent i){if(i==null||!ACTION.equals(i.getAction()))return;long now=System.currentTimeMillis();if(!MorningDiarySchedule.inWindow(now)){scheduleInitial(c,now);return;}
        String state=MorningDiaryStore.today(c,today(now));if(MorningDiaryStore.WRITTEN.equals(state))NotificationManagerCompat.from(c).cancel(NOTIFICATION);else notifyMissing(c,UNKNOWN.equals(state));
        scheduleAt(c,MorningDiarySchedule.nextCheck(now));
    }
    private static final String UNKNOWN=MorningDiaryStore.UNKNOWN;
    private static void notifyMissing(Context c,boolean unknown){
        if(Build.VERSION.SDK_INT>=26)c.getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel("morning_diary_reminder","晨间日记提醒",NotificationManager.IMPORTANCE_HIGH));
        Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(c,"morning_diary_reminder"):new Notification.Builder(c);
        Intent open=new Intent(c,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent tap=PendingIntent.getActivity(c,REQUEST,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification n=b.setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("晨间日志提醒").setContentText(unknown?"暂时无法确认，请补写今天的晨间日志。":"今天的晨间日记还没有写，请现在补写。").setContentIntent(tap).setAutoCancel(true).build();
        NotificationManagerCompat.from(c).notify(NOTIFICATION,n);
    }
}
