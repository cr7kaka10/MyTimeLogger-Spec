package com.mytimelogger.app;

import android.app.*;
import android.content.*;
import android.os.Build;

final class SleepAutomationNotificationFactory {
    static final String EXTRA_RUN_KEY="run_key",STOP="sleep.stop",RETRY="sleep.retry",MANUAL="sleep.manual";
    static boolean matchesRun(String expected,String supplied){return expected!=null&&expected.equals(supplied);}
    static Notification build(Context c,String channel,String stage,String reason,String runKey){
        Intent stop=new Intent(c,SleepAutomationRunnerService.class).setAction(STOP).putExtra(EXTRA_RUN_KEY,runKey),retry=new Intent(c,SleepAutomationRunnerService.class).setAction(RETRY).putExtra(EXTRA_RUN_KEY,runKey).putExtra(SleepAutomationRunnerService.EXTRA_STAGE,"PENDING"),manual=new Intent(c,MainActivity.class).setAction(MANUAL).putExtra(EXTRA_RUN_KEY,runKey);
        int flags=PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE,base=runKey==null?0:runKey.hashCode();
        PendingIntent pStop=PendingIntent.getService(c,base+1,stop,flags),pRetry=PendingIntent.getService(c,base+2,retry,flags),pManual=PendingIntent.getActivity(c,base+3,manual,flags);
        Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(c,channel):new Notification.Builder(c);
        return b.setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("睡眠自动化")
                .setContentText("阶段："+stage+(reason==null||reason.isEmpty()?"":"；原因："+reason)).setOngoing(!"SUCCESS".equals(stage))
                .addAction(0,"停止",pStop).addAction(0,"立即重试",pRetry).addAction(0,"手工上传",pManual).build();
    }
    private SleepAutomationNotificationFactory(){}
}
