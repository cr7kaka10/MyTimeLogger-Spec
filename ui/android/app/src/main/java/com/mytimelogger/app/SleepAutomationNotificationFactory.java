package com.mytimelogger.app;

import android.app.*;
import android.content.*;
import android.os.Build;
import androidx.core.app.NotificationManagerCompat;

final class SleepAutomationNotificationFactory {
    static final String EXTRA_RUN_KEY="run_key",STOP="sleep.stop",RETRY="sleep.retry",MANUAL="sleep.manual",RESULT_CHANNEL="sleep_automation_result";
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
    static String resultTitle(boolean success){return success?"今日睡眠报告生成成功":"今日睡眠报告生成失败";}
    static String resultText(boolean success,String reason){return success?"今日睡眠报告已生成":"报告未生成；原因："+reasonText(reason);}
    static void showResult(Context c,boolean success,String reason){
        showMessage(c,resultTitle(success),resultText(success,reason),842);
    }
    static String statusUnknownTitle(){return "睡眠报告状态暂不可确认";}
    static String statusUnknownText(String reason){return "请稍后检查睡眠页；原因："+reasonText(reason);}
    static void showStatusUnknown(Context c,String reason){showMessage(c,statusUnknownTitle(),statusUnknownText(reason),842);}
    static String captureResultTitle(boolean success){return success?"睡眠图片采集成功":"睡眠图片采集失败";}
    static String captureResultText(boolean success,String reason){return success?"今日采集图片已保存":"图片未保存；原因："+reasonText(reason);}
    static void showCaptureResult(Context c,boolean success,String reason){
        showMessage(c,captureResultTitle(success),captureResultText(success,reason));
    }
    static void showUnlockReminder(Context c){showMessage(c,"请解锁手机","请在 08:40 前解锁，随后将自动开始睡眠分析。",835);}
    private static String reasonText(String reason){return reason==null||reason.isEmpty()?"未知":reason.substring(0,Math.min(48,reason.length()));}
    private static void showMessage(Context c,String title,String text){
        showMessage(c,title,text,(int)(System.currentTimeMillis()&0x7fffffff));
    }
    private static void showMessage(Context c,String title,String text,int id){
        try{
            if(Build.VERSION.SDK_INT>=26){NotificationChannel channel=new NotificationChannel(RESULT_CHANNEL,"睡眠报告结果",NotificationManager.IMPORTANCE_HIGH);channel.setDescription("今日睡眠报告生成成功或失败时提醒");c.getSystemService(NotificationManager.class).createNotificationChannel(channel);}
            Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(c,RESULT_CHANNEL):new Notification.Builder(c);
            Notification result=b.setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle(title).setContentText(text).setAutoCancel(true).setCategory(Notification.CATEGORY_STATUS).setPriority(Notification.PRIORITY_HIGH).build();
            NotificationManagerCompat.from(c).notify(id,result);
        }catch(SecurityException ignored){}
    }
    private SleepAutomationNotificationFactory(){}
}
