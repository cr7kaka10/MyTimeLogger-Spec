package com.mytimelogger.app;

import android.Manifest;
import android.app.*;
import android.content.Context;
import android.content.Intent;
import android.app.PendingIntent;
import android.content.pm.PackageManager;
import android.os.*;
import androidx.core.app.NotificationManagerCompat;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

public final class SleepAutomationRunnerService extends Service {
    static final String CHANNEL = "sleep_automation", EXTRA_STAGE = "stage";
    static final String AUTOMATION_REVISION = "sleep-auto-20261024.4", TEST_ACTION = "sleep.test";
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private PowerManager.WakeLock wakeLock;
    private String runKey;
    private boolean keepNotification;

    @Override public void onCreate() {
        super.onCreate();
        runKey="android-huawei:"+today();
        if (Build.VERSION.SDK_INT >= 26) getSystemService(NotificationManager.class).createNotificationChannel(
                new NotificationChannel(CHANNEL, "睡眠自动化", NotificationManager.IMPORTANCE_LOW));
        startForeground(840, notification("PENDING"));
        wakeLock = ((PowerManager) getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MyTimeLogger:sleep");
        wakeLock.acquire(20L * 60L * 1000L);
    }

    Notification notification(String stage) {
        String[] p=normalizeStage(stage).split(":",2);return SleepAutomationNotificationFactory.build(this,CHANNEL,p[0],p.length>1?p[1]:"",runKey);
    }
    private String today(){SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd",Locale.ROOT);f.setTimeZone(SleepAutomationScheduler.BEIJING);return f.format(new Date());}

    static String decide(boolean... ok) {
        String[] codes = {"accessibility_unavailable","notifications_denied","media_permission_limited","login_required","huawei_not_installed","device_locked","already_succeeded"};
        for (int i=0;i<codes.length;i++) if (!ok[i]) return codes[i]; return "ok";
    }
    static boolean needsCapture(SleepAutomationSnapshot s){return s==null||s.mediaUri==null||s.mediaUri.isEmpty();}
    static boolean acceptsMedia(String code){return "ok".equals(code);}
    static String nextNetworkAction(SleepAutomationSnapshot s){if(s!=null&&s.requestId!=null&&!s.requestId.isEmpty())return "poll";return s!=null&&s.mediaUri!=null&&!s.mediaUri.isEmpty()?"upload":"capture";}
    static String outcome(String state,boolean reportReady){if(("done".equals(state)||"reused".equals(state))&&reportReady)return "SUCCESS";if(java.util.Arrays.asList("queued","running","done","reused","timeout","network_error","server_error").contains(state))return "POLLING";return "FAILED";}
    static String normalizeStage(String value){
        String stage=value==null?"":value.trim();if(stage.isEmpty())return "PENDING";
        String base=stage.split(":",2)[0];return Arrays.asList("PENDING","FAILED","SUCCESS","POLLING","MEDIA","UPLOADED").contains(base)?stage:"PENDING";
    }
    static String startSource(String action){if(SleepAutomationAlarmReceiver.ACTION.equals(action))return "main_alarm";if(SleepAutomationAlarmReceiver.RETRY_ACTION.equals(action))return "retry_alarm";if(SleepAutomationNotificationFactory.RETRY.equals(action))return "notification_retry";if(TEST_ACTION.equals(action))return "manual_test";return "system_restart";}
    static long nextRetry(long now,String reason){if(!reason.startsWith("capture_timeout_")&&!Arrays.asList("device_locked","media_not_found","media_not_stable","sleep_data_not_ready","save_not_observed","queued","running","done","reused","timeout","network_error","server_error").contains(reason))return -1;Calendar c=Calendar.getInstance(SleepAutomationScheduler.BEIJING);c.setTimeInMillis(now);Calendar deadline=(Calendar)c.clone();deadline.set(Calendar.HOUR_OF_DAY,23);deadline.set(Calendar.MINUTE,45);deadline.set(Calendar.SECOND,0);deadline.set(Calendar.MILLISECOND,0);long interval=c.get(Calendar.HOUR_OF_DAY)<9?5L:15L;long next=now+interval*60_000L;return next<deadline.getTimeInMillis()?next:-1;}
    static PendingIntent retryPending(Context c){Intent i=new Intent(c,SleepAutomationAlarmReceiver.class).setAction(SleepAutomationAlarmReceiver.RETRY_ACTION);return PendingIntent.getBroadcast(c,841,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
    private void scheduleRetry(String reason){long at=nextRetry(System.currentTimeMillis(),reason);SleepAutomationStateStore states=new SleepAutomationStateStore(this);states.setNextRetryAt(at);if(at<0){SleepAutomationSnapshot s=states.load(today());if(s!=null&&"POLLING".equals(s.stage)){states.save(new SleepAutomationSnapshot("FAILED",s.sleepDate,s.mediaUri,s.requestId,s.attempt,"retry_window_elapsed",System.currentTimeMillis()));keepNotification=true;startForeground(840,notification("FAILED:retry_window_elapsed"));}return;}((AlarmManager)getSystemService(ALARM_SERVICE)).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,at,retryPending(this));}
    private void notifyFailure(String reason){keepNotification=true;startForeground(840,notification("FAILED:"+reason));}

    private String gate() {
        boolean accessibility = SleepAutomationAccessibility.isEnabled(this);
        boolean images = Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED;
        boolean version = false; try { version = getPackageManager().getPackageInfo("com.huawei.health",0).versionName!=null; } catch(Exception ignored) {}
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT); f.setTimeZone(SleepAutomationScheduler.BEIJING);
        SleepAutomationSnapshot s = new SleepAutomationStateStore(this).load(f.format(new Date()));
        return decide(accessibility, NotificationManagerCompat.from(this).areNotificationsEnabled(), images,
                true, version,
                !((KeyguardManager)getSystemService(KEYGUARD_SERVICE)).isDeviceLocked(), s==null || !"SUCCESS".equals(s.stage));
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        String action=intent==null?"":intent.getAction();if((SleepAutomationNotificationFactory.STOP.equals(action)||SleepAutomationNotificationFactory.RETRY.equals(action))&&!SleepAutomationNotificationFactory.matchesRun(runKey,intent.getStringExtra(SleepAutomationNotificationFactory.EXTRA_RUN_KEY)))return START_NOT_STICKY;if(SleepAutomationNotificationFactory.STOP.equals(action)){stopSelf(id);return START_NOT_STICKY;}
        new SleepAutomationStateStore(this).recordStartSource(startSource(action));
        String blocked = gate();
        startForeground(840, notification("ok".equals(blocked) ? normalizeStage(intent == null ? null : intent.getStringExtra(EXTRA_STAGE)) : "FAILED:" + blocked));
        if (!"ok".equals(blocked)){SleepAutomationStateStore states=new SleepAutomationStateStore(this);SleepAutomationSnapshot old=states.load(today());states.advance(new SleepAutomationSnapshot("FAILED",today(),old==null?"":old.mediaUri,old==null?"":old.requestId,old==null?1:old.attempt+1,blocked,System.currentTimeMillis()));keepNotification=true;scheduleRetry(blocked);stopSelf(id);}else worker.execute(this::capture);
        return START_NOT_STICKY;
    }

    private void capture(){
        SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd",Locale.ROOT);f.setTimeZone(SleepAutomationScheduler.BEIJING);String date=f.format(new Date());SleepAutomationStateStore states=new SleepAutomationStateStore(this);SleepAutomationSnapshot old=states.load(date);
        if(!needsCapture(old)){transfer(old,states);return;}
        SleepAutomationMediaRepository media=new SleepAutomationMediaRepository(getContentResolver());SleepAutomationMediaRepository.Baseline baseline=media.baseline(System.currentTimeMillis());String command=HuaweiSleepAutomationService.send("LAUNCH_HEALTH");if(!"ok".equals(command)){states.save(new SleepAutomationSnapshot("FAILED",date,"","",1,command,System.currentTimeMillis()));notifyFailure(command);stopSelf();return;}
        long deadline=System.currentTimeMillis()+60000;String reason="media_not_found";
        try{while(System.currentTimeMillis()<deadline){SleepAutomationMediaRepository.Result result=media.select(media.candidates(baseline,System.currentTimeMillis()),true);reason=result.code;if(acceptsMedia(reason)){SleepAutomationSnapshot saved=new SleepAutomationSnapshot("MEDIA",date,result.candidate.uri,"",1,"",System.currentTimeMillis());states.save(saved);transfer(saved,states);return;}HuaweiSleepAutomationService.Snapshot a=HuaweiSleepAutomationService.snapshot();if(a.failure!=null){reason=a.failure;break;}if("media_ambiguous".equals(reason)||"media_permission_limited".equals(reason))break;Thread.sleep(1000);}if("media_not_found".equals(reason)){HuaweiSleepAutomationService.Snapshot a=HuaweiSleepAutomationService.snapshot();reason="SAVED".equals(a.step)?"save_not_observed":"capture_timeout_"+(a.step==null?"unknown":a.step.toLowerCase(Locale.ROOT));}}catch(Exception e){reason="media_query_failed";}
        states.save(new SleepAutomationSnapshot("FAILED",date,"","",1,reason,System.currentTimeMillis()));scheduleRetry(reason);notifyFailure(reason);stopSelf();
    }

    private void transfer(SleepAutomationSnapshot current,SleepAutomationStateStore states){
        String[] secret=new SleepAutomationSecretStore(this).read();if(secret==null){states.save(new SleepAutomationSnapshot("FAILED",current.sleepDate,current.mediaUri,current.requestId,current.attempt,"login_required",System.currentTimeMillis()));notifyFailure("login_required");stopSelf();return;}SleepAutomationApiClient api=new SleepAutomationApiClient(getContentResolver());
        if("upload".equals(nextNetworkAction(current))){SleepAutomationApiClient.Job job=SleepAutomationApiClient.uploadJob(api.upload(current.mediaUri,current.sleepDate,secret[0],secret[1]));if(job.requestId.isEmpty()){boolean retry="POLLING".equals(outcome(job.state,false));states.save(new SleepAutomationSnapshot(retry?"POLLING":"FAILED",current.sleepDate,current.mediaUri,"",current.attempt,job.state,System.currentTimeMillis()));if(retry)scheduleRetry(job.state);else notifyFailure(job.state);stopSelf();return;}current=new SleepAutomationSnapshot("UPLOADED",current.sleepDate,current.mediaUri,job.requestId,current.attempt,job.state,System.currentTimeMillis());states.save(current);}
        SleepAutomationApiClient.Job status=SleepAutomationApiClient.statusJob(api.status(current.requestId,current.sleepDate,secret[0],secret[1]),current.sleepDate);String stage=outcome(status.state,status.reportReady),reason=("done".equals(status.state)||"reused".equals(status.state))&&!status.reportReady?"full_report_pending":status.state;states.advance(new SleepAutomationSnapshot(stage,current.sleepDate,current.mediaUri,current.requestId,current.attempt,"SUCCESS".equals(stage)?"":reason,System.currentTimeMillis()));keepNotification=!"POLLING".equals(stage);startForeground(840,notification(stage+("SUCCESS".equals(stage)?"":":"+reason)));if("POLLING".equals(stage))scheduleRetry(status.state);stopSelf();
    }

    @Override public android.os.IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() {
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        worker.shutdownNow(); stopForeground(keepNotification?STOP_FOREGROUND_DETACH:STOP_FOREGROUND_REMOVE); super.onDestroy();
    }
}
