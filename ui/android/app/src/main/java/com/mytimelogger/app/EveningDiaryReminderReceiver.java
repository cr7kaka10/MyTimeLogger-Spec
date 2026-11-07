package com.mytimelogger.app;

import android.app.*;
import android.content.*;
import android.os.Build;
import androidx.core.app.NotificationManagerCompat;
import com.google.gson.*;
import java.util.Calendar;

public final class EveningDiaryReminderReceiver extends BroadcastReceiver {
    static final String ACTION="com.mytimelogger.EVENING_DIARY_CHECK";
    static final int REQUEST=851, NOTIFICATION=851;
    static final long INTERVAL_MS=5L*60L*1000L;
    private static volatile boolean foreground;
    static void setForeground(boolean value){foreground=value;}
    static PendingIntent pending(Context c){Intent i=new Intent(c,EveningDiaryReminderReceiver.class).setAction(ACTION);return PendingIntent.getBroadcast(c,REQUEST,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
    static long eveningStart(long now){Calendar day=Calendar.getInstance(SleepAutomationScheduler.BEIJING);day.setTimeInMillis(now);day.set(Calendar.HOUR_OF_DAY,18);day.set(Calendar.MINUTE,0);day.set(Calendar.SECOND,0);day.set(Calendar.MILLISECOND,0);return day.getTimeInMillis();}
    static long tomorrowStart(long now){Calendar day=Calendar.getInstance(SleepAutomationScheduler.BEIJING);day.setTimeInMillis(now);day.add(Calendar.DAY_OF_MONTH,1);return eveningStart(day.getTimeInMillis());}
    static long nextCheck(long now){long start=eveningStart(now);if(now<start)return start;return now+INTERVAL_MS<tomorrowStart(now)-18L*60L*60L*1000L?now+INTERVAL_MS:tomorrowStart(now);}
    static void scheduleAt(Context c,long at){AlarmManager a=(AlarmManager)c.getSystemService(Context.ALARM_SERVICE);if(Build.VERSION.SDK_INT<31||a.canScheduleExactAlarms())a.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,at,pending(c));else a.setWindow(AlarmManager.RTC_WAKEUP,at,60_000,pending(c));}
    static void reconcile(Context c){scheduleAt(c,Math.max(System.currentTimeMillis()+1000,eveningStart(System.currentTimeMillis())));}
    static void cancel(Context c){((AlarmManager)c.getSystemService(Context.ALARM_SERVICE)).cancel(pending(c));NotificationManagerCompat.from(c).cancel(NOTIFICATION);}
    @Override public void onReceive(Context context,Intent intent){if(intent==null||!ACTION.equals(intent.getAction()))return;PendingResult result=goAsync();Context c=context.getApplicationContext();new Thread(()->{try{check(c);}finally{result.finish();}},"evening-diary-check").start();}
    private static void check(Context c){long now=System.currentTimeMillis();if(now<eveningStart(now)){scheduleAt(c,eveningStart(now));return;}String date=MorningDiaryReminderReceiver.today(now);String local=EveningDiaryStore.today(c,date);
        if(EveningDiaryStore.UNKNOWN.equals(local)){NotificationManagerCompat.from(c).cancel(NOTIFICATION);scheduleAt(c,nextCheck(now));return;}
        if(EveningDiaryStore.WRITTEN.equals(local)){cancel(c);scheduleAt(c,tomorrowStart(now));return;}
        String remote=remoteState(c,date);if(EveningDiaryStore.WRITTEN.equals(remote)){cancel(c);scheduleAt(c,tomorrowStart(now));return;}
        if(EveningDiaryStore.READY.equals(local)||EveningDiaryStore.READY.equals(remote)){if(!foreground||!EveningDiaryStore.READY.equals(local))notifyMissing(c);}
        else NotificationManagerCompat.from(c).cancel(NOTIFICATION);
        scheduleAt(c,nextCheck(now));
    }
    private static String remoteState(Context c,String date){WidgetTimerRuntimeStore.Config runtime=new WidgetTimerRuntimeStore(c).read();if(runtime==null)return EveningDiaryStore.UNKNOWN;
        try{SleepAutomationApiClient.Result response=new SleepAutomationApiClient(c.getContentResolver()).statusByDate(date,runtime.serverUrl,runtime.authToken,4000);if(!"ok".equals(response.code))return EveningDiaryStore.UNKNOWN;
            JsonObject job=JsonParser.parseString(response.body).getAsJsonObject();if(!date.equals(job.get("date").getAsString()))return EveningDiaryStore.UNKNOWN;
            JsonObject data=job.getAsJsonObject("result");if(data==null)return EveningDiaryStore.UNKNOWN;
            Number status=data.has("report_status")&&!data.get("report_status").isJsonNull()?data.get("report_status").getAsNumber():null;
            String full=data.has("full_report_state")&&!data.get("full_report_state").isJsonNull()?data.get("full_report_state").getAsString():null;
            String diary=data.has("evening_diary")&&!data.get("evening_diary").isJsonNull()?data.get("evening_diary").getAsString():null;
            return EveningDiaryStore.classify(status,full,diary);
        }catch(Exception ignored){return EveningDiaryStore.UNKNOWN;}
    }
    private static void notifyMissing(Context c){if(!NotificationManagerCompat.from(c).areNotificationsEnabled())return;
        if(Build.VERSION.SDK_INT>=26)c.getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel("evening_diary_reminder","晚间日记提醒",NotificationManager.IMPORTANCE_HIGH));
        Intent open=new Intent(c,MainActivity.class).putExtra("route","timer").putExtra("evening_diary",true).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent tap=PendingIntent.getActivity(c,REQUEST,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(c,"evening_diary_reminder"):new Notification.Builder(c);
        Notification n=b.setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("全天报告已生成").setContentText("晚间日记还没写，点此填写。").setContentIntent(tap).setPriority(Notification.PRIORITY_HIGH).setAutoCancel(true).build();
        try{NotificationManagerCompat.from(c).notify(NOTIFICATION,n);}catch(SecurityException ignored){}
    }
}
