package com.mytimelogger.app;

import android.Manifest;
import android.app.*;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.content.res.AssetFileDescriptor;
import android.app.PendingIntent;
import android.content.pm.PackageManager;
import android.os.*;
import androidx.core.app.NotificationManagerCompat;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SleepAutomationRunnerService extends Service {
    static final String CHANNEL = "sleep_automation", EXTRA_STAGE = "stage";
    static final String AUTOMATION_REVISION = "sleep-auto-20261026.1", TEST_ACTION = "sleep.test", CAPTURE_ONLY_ACTION = "sleep.capture_only", GENERATE_REPORT_ACTION = "sleep.generate_report", ONE_CLICK_ACTION = "sleep.one_click";
    static final int MAX_AUTO_RETRIES = 3, MAX_AUTO_ATTEMPTS = MAX_AUTO_RETRIES + 1;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final AtomicBoolean captureInProgress = new AtomicBoolean();
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
    static boolean retryableReportError(String reason){return Arrays.asList("ocr_failed","model_provider_error","report_failed").contains(reason);}
    static String nextNetworkAction(SleepAutomationSnapshot s){if(s!=null&&s.requestId!=null&&!s.requestId.isEmpty())return "FAILED".equals(s.stage)?"retry_report":"poll";return s!=null&&s.mediaUri!=null&&!s.mediaUri.isEmpty()?"upload":"capture";}
    static String outcome(String state,boolean reportReady){if(("done".equals(state)||"reused".equals(state))&&reportReady)return "SUCCESS";if(java.util.Arrays.asList("queued","running","done","reused","timeout","network_error","server_error").contains(state))return "POLLING";return "FAILED";}
    static boolean isTodaySavedProbe(SleepCaptureProbeStore.Snapshot probe,String today){return probe!=null&&"SAVED".equals(probe.stage)&&today!=null&&today.equals(probe.date)&&probe.uri!=null&&!probe.uri.isEmpty();}
    static String normalizeStage(String value){
        String stage=value==null?"":value.trim();if(stage.isEmpty())return "PENDING";
        String base=stage.split(":",2)[0];return Arrays.asList("PENDING","FAILED","SUCCESS","POLLING","MEDIA","UPLOADED").contains(base)?stage:"PENDING";
    }
    static String startSource(String action){if(SleepAutomationAlarmReceiver.ACTION.equals(action))return "main_alarm";if(SleepAutomationAlarmReceiver.RETRY_ACTION.equals(action))return "retry_alarm";if(SleepAutomationNotificationFactory.RETRY.equals(action))return "notification_retry";if(TEST_ACTION.equals(action))return "manual_test";return "system_restart";}
    static int nextRetryAttempt(int completedAttempt){return completedAttempt<MAX_AUTO_ATTEMPTS?Math.max(1,completedAttempt+1):-1;}
    static int nextRetryAttempt(int completedAttempt,String reason){return Arrays.asList("queued","running","done","reused","sleep_report_pending","ocr_pending","report_request_pending").contains(reason)?Math.max(1,completedAttempt):nextRetryAttempt(completedAttempt);}
    static long nextRetry(long now,String reason){if(reason==null||reason.isEmpty()||"SUCCESS".equals(reason))return -1;Calendar c=Calendar.getInstance(SleepAutomationScheduler.BEIJING);c.setTimeInMillis(now);Calendar deadline=(Calendar)c.clone();deadline.set(Calendar.HOUR_OF_DAY,23);deadline.set(Calendar.MINUTE,45);deadline.set(Calendar.SECOND,0);deadline.set(Calendar.MILLISECOND,0);long interval=c.get(Calendar.HOUR_OF_DAY)<9?5L:15L;long next=now+interval*60_000L;return next<deadline.getTimeInMillis()?next:-1;}
    static PendingIntent retryPending(Context c){Intent i=new Intent(c,SleepAutomationAlarmReceiver.class).setAction(SleepAutomationAlarmReceiver.RETRY_ACTION);return PendingIntent.getBroadcast(c,841,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
    private void scheduleRetry(String reason){
        long now=System.currentTimeMillis();SleepAutomationStateStore states=new SleepAutomationStateStore(this);SleepAutomationSnapshot s=states.load(today());
        if(s==null){notifyFinalResult(false,reason);return;}
        int nextAttempt=nextRetryAttempt(s.attempt,reason);long at=nextAttempt<0?-1:nextRetry(now,reason);
        if(at<0){String terminal=nextAttempt<0?reason:"retry_window_elapsed";states.save(new SleepAutomationSnapshot("FAILED",s.sleepDate,s.mediaUri,s.requestId,Math.max(1,s.attempt),terminal,now));states.setNextRetryAt(-1);notifyFinalResult(false,terminal);return;}
        String stage=s.requestId!=null&&!s.requestId.isEmpty()&&"FAILED".equals(s.stage)?"FAILED":"POLLING";
        states.save(new SleepAutomationSnapshot(stage,s.sleepDate,s.mediaUri,s.requestId,nextAttempt,reason,now,s.mode));states.setNextRetryAt(at);keepNotification=true;startForeground(840,notification("POLLING:"+reason));
        ((AlarmManager)getSystemService(ALARM_SERVICE)).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,at,retryPending(this));
    }
    private String reportStateToday(){String[] secret=new SleepAutomationSecretStore(this).read();if(secret==null)return "unknown";SleepAutomationApiClient api=new SleepAutomationApiClient(getContentResolver());return SleepAutomationApiClient.dateReportState(api.statusByDate(today(),secret[0],secret[1]),today());}
    private void notifyFinalResult(boolean success,String reason){
        if(!success){String report=reportStateToday();if("ready".equals(report))success=true;else if("unknown".equals(report)){keepNotification=true;startForeground(840,notification("POLLING:report_status_unknown"));SleepAutomationNotificationFactory.showStatusUnknown(this,reason);return;}}
        keepNotification=true;String stage=success?"SUCCESS":"FAILED:"+reason;startForeground(840,notification(stage));SleepAutomationNotificationFactory.showResult(this,success,reason);
    }
    private void notifyFailure(String reason){notifyFinalResult(false,reason);}
    static final class CaptureOutcome {
        final String code;final SleepAutomationMediaRepository.Candidate candidate;final SleepAutomationMediaRepository.Inspection image;
        CaptureOutcome(String reason,SleepAutomationMediaRepository.Candidate file,SleepAutomationMediaRepository.Inspection info){code=reason;candidate=file;image=info;}
    }
    private CaptureOutcome captureImage(String date){
        SleepAutomationMediaRepository media=new SleepAutomationMediaRepository(getContentResolver());
        try{
            SleepAutomationMediaRepository.Baseline baseline=media.baseline(System.currentTimeMillis());
            String command=HuaweiSleepAutomationService.send("LAUNCH_HEALTH");if(!"ok".equals(command))return new CaptureOutcome(command,null,null);
            long deadline=System.currentTimeMillis()+60000;String reason="media_not_found";
            while(System.currentTimeMillis()<deadline){
                long now=System.currentTimeMillis();HuaweiSleepAutomationService.Snapshot stage=HuaweiSleepAutomationService.snapshot();
                if(stage.failure!=null){reason=stage.failure;break;}
                SleepAutomationMediaRepository.Result result=media.select(media.candidates(baseline,now,date),true);reason=result.code;
                if(acceptsMedia(reason)&&"SAVED".equals(stage.step)&&stage.saveStartedAt>0&&result.candidate.addedAt>=stage.saveStartedAt-1000){
                    SleepAutomationMediaRepository.Inspection image=media.inspect(result.candidate);
                    if("ok".equals(image.code))return new CaptureOutcome("ok",result.candidate,image);
                    reason=image.code;break;
                }
                if("media_ambiguous".equals(reason)||"media_permission_limited".equals(reason))break;
                Thread.sleep(1000);
            }
            if("media_not_found".equals(reason)||"ok".equals(reason)){HuaweiSleepAutomationService.Snapshot stage=HuaweiSleepAutomationService.snapshot();reason="SAVED".equals(stage.step)?"save_not_observed":"capture_timeout_"+(stage.step==null?"unknown":stage.step.toLowerCase(Locale.ROOT));}
            return new CaptureOutcome(reason,null,null);
        }catch(Exception e){return new CaptureOutcome("media_query_failed",null,null);}
    }

    private String gate(boolean captureOnly) {
        boolean accessibility = SleepAutomationAccessibility.isEnabled(this);
        boolean images = Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED;
        boolean version = false; try { version = getPackageManager().getPackageInfo("com.huawei.health",0).versionName!=null; } catch(Exception ignored) {}
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT); f.setTimeZone(SleepAutomationScheduler.BEIJING);
        SleepAutomationSnapshot s = new SleepAutomationStateStore(this).load(f.format(new Date()));
        return decide(accessibility, NotificationManagerCompat.from(this).areNotificationsEnabled(), images,
                true, version,
                !((KeyguardManager)getSystemService(KEYGUARD_SERVICE)).isDeviceLocked(), captureOnly||s==null || !"SUCCESS".equals(s.stage));
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        String action=intent==null?"":intent.getAction();if((SleepAutomationNotificationFactory.STOP.equals(action)||SleepAutomationNotificationFactory.RETRY.equals(action))&&!SleepAutomationNotificationFactory.matchesRun(runKey,intent.getStringExtra(SleepAutomationNotificationFactory.EXTRA_RUN_KEY)))return START_NOT_STICKY;if(SleepAutomationNotificationFactory.STOP.equals(action)){stopSelf(id);return START_NOT_STICKY;}
        if(GENERATE_REPORT_ACTION.equals(action)){
            if(!captureInProgress.compareAndSet(false,true))return START_NOT_STICKY;
            startForeground(840,notification("PENDING"));worker.execute(()->{try{generateReportFromProbe();}finally{captureInProgress.set(false);}});return START_NOT_STICKY;
        }
        if(CAPTURE_ONLY_ACTION.equals(action)||ONE_CLICK_ACTION.equals(action)){
            if(!captureInProgress.compareAndSet(false,true))return START_NOT_STICKY;
            SleepCaptureProbeStore probes=new SleepCaptureProbeStore(this);SleepCaptureProbeStore.Snapshot run=probes.start(today());String blocked=gate(true);
            if(!"ok".equals(blocked)){probes.finish(run,"FAILED",blocked,"",0,0,0);captureInProgress.set(false);startForeground(840,notification("FAILED:"+blocked));stopSelf(id);}
            else {startForeground(840,notification("PENDING"));boolean oneClick=ONE_CLICK_ACTION.equals(action);worker.execute(()->captureOnly(probes,run,oneClick));}
            return START_NOT_STICKY;
        }
        new SleepAutomationStateStore(this).recordStartSource(startSource(action));
        SleepAutomationSnapshot pending=new SleepAutomationStateStore(this).load(today());
        boolean resume=pending!=null&&pending.mode!=null&&!pending.mode.isEmpty()&&!needsCapture(pending);
        String blocked = resume?"ok":gate(false);
        startForeground(840, notification("ok".equals(blocked) ? normalizeStage(intent == null ? null : intent.getStringExtra(EXTRA_STAGE)) : "FAILED:" + blocked));
        if("already_succeeded".equals(blocked)){stopSelf(id);return START_NOT_STICKY;}
        if (!"ok".equals(blocked)){worker.execute(()->{SleepAutomationStateStore states=new SleepAutomationStateStore(this);SleepAutomationSnapshot old=states.load(today());states.advance(new SleepAutomationSnapshot("FAILED",today(),old==null?"":old.mediaUri,old==null?"":old.requestId,old==null?1:old.attempt,blocked,System.currentTimeMillis()));scheduleRetry(blocked);stopSelf(id);});}else worker.execute(this::capture);
        return START_NOT_STICKY;
    }

    private void capture(){
        SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd",Locale.ROOT);f.setTimeZone(SleepAutomationScheduler.BEIJING);String date=f.format(new Date());SleepAutomationStateStore states=new SleepAutomationStateStore(this);SleepAutomationSnapshot old=states.load(date);
        if(!needsCapture(old)){transfer(old,states);return;}
        CaptureOutcome outcome=captureImage(date);
        int attempt=old==null?1:Math.max(1,old.attempt);
        if("ok".equals(outcome.code)){SleepAutomationSnapshot saved=new SleepAutomationSnapshot("MEDIA",date,outcome.candidate.uri,"",attempt,"",System.currentTimeMillis());states.save(saved);transfer(saved,states);return;}
        states.save(new SleepAutomationSnapshot("FAILED",date,"","",attempt,outcome.code,System.currentTimeMillis()));scheduleRetry(outcome.code);stopSelf();
    }

    private void captureOnly(SleepCaptureProbeStore probes,SleepCaptureProbeStore.Snapshot run,boolean oneClick){
        try{
            CaptureOutcome result=captureImage(run.date);
            if("ok".equals(result.code)){
                probes.finish(run,"SAVED","",result.candidate.uri,System.currentTimeMillis(),result.image.width,result.image.height);
                startForeground(840,notification("MEDIA"));
                if(oneClick){HuaweiSleepAutomationService.openSleepPage();generateReportFromProbe(true);}
                else SleepAutomationNotificationFactory.showCaptureResult(this,true,"");
            }else{
                probes.finish(run,"FAILED",result.code,"",0,0,0);keepNotification=true;startForeground(840,notification("FAILED:"+result.code));SleepAutomationNotificationFactory.showCaptureResult(this,false,result.code);
            }
        }finally{captureInProgress.set(false);stopSelf();}
    }

    private void generateReportFromProbe(){generateReportFromProbe(false);}
    private void generateReportFromProbe(boolean validateFirst){
        SleepCaptureProbeStore probes=new SleepCaptureProbeStore(this);SleepCaptureProbeStore.Snapshot probe=probes.load();
        if(!isTodaySavedProbe(probe,today())){notifyFailure("capture_required");stopSelf();return;}
        try(AssetFileDescriptor fd=getContentResolver().openAssetFileDescriptor(Uri.parse(probe.uri),"r")){
            if(fd==null||fd.getLength()<=0){probes.finish(probe,"FAILED","media_unreadable","",0,0,0);notifyFailure("media_unreadable");stopSelf();return;}
        }catch(Exception e){probes.finish(probe,"FAILED","media_unreadable","",0,0,0);notifyFailure("media_unreadable");stopSelf();return;}
        SleepAutomationStateStore states=new SleepAutomationStateStore(this);SleepAutomationSnapshot media=new SleepAutomationSnapshot("MEDIA",probe.date,probe.uri,"",1,"",System.currentTimeMillis(),validateFirst?"ocr":"");states.save(media);transfer(media,states);
    }

    private void transfer(SleepAutomationSnapshot current,SleepAutomationStateStore states){
        if(current.mode!=null&&!current.mode.isEmpty()){transferSequential(current,states);return;}
        String[] secret=new SleepAutomationSecretStore(this).read();if(secret==null){states.save(new SleepAutomationSnapshot("FAILED",current.sleepDate,current.mediaUri,current.requestId,current.attempt,"login_required",System.currentTimeMillis()));scheduleRetry("login_required");stopSelf();return;}SleepAutomationApiClient api=new SleepAutomationApiClient(getContentResolver());
        if("retry_report".equals(nextNetworkAction(current))){SleepAutomationApiClient.Job retry=SleepAutomationApiClient.uploadJob(api.retryReport(current.sleepDate,secret[0],secret[1]));if(retry.requestId.isEmpty()){String reason=retryableReportError(retry.state)?retry.state:current.reason;states.save(new SleepAutomationSnapshot("FAILED",current.sleepDate,current.mediaUri,current.requestId,current.attempt,reason,System.currentTimeMillis()));scheduleRetry(retry.state);stopSelf();return;}current=new SleepAutomationSnapshot("UPLOADED",current.sleepDate,current.mediaUri,retry.requestId,current.attempt,retry.state,System.currentTimeMillis());states.save(current);}
        if("upload".equals(nextNetworkAction(current))){SleepAutomationApiClient.Job job=SleepAutomationApiClient.uploadJob(api.upload(current.mediaUri,current.sleepDate,secret[0],secret[1]));if(job.requestId.isEmpty()){String stage="POLLING".equals(outcome(job.state,false))?"POLLING":"FAILED";states.save(new SleepAutomationSnapshot(stage,current.sleepDate,current.mediaUri,"",current.attempt,job.state,System.currentTimeMillis()));scheduleRetry(job.state);stopSelf();return;}current=new SleepAutomationSnapshot("UPLOADED",current.sleepDate,current.mediaUri,job.requestId,current.attempt,job.state,System.currentTimeMillis());states.save(current);}
        SleepAutomationApiClient.Job status=SleepAutomationApiClient.statusJob(api.status(current.requestId,current.sleepDate,secret[0],secret[1]),current.sleepDate);String stage=outcome(status.state,status.reportReady),reason=("done".equals(status.state)||"reused".equals(status.state))&&!status.reportReady?"sleep_report_pending":status.state;states.advance(new SleepAutomationSnapshot(stage,current.sleepDate,current.mediaUri,current.requestId,current.attempt,"SUCCESS".equals(stage)?"":reason,System.currentTimeMillis()));if("SUCCESS".equals(stage))notifyFinalResult(true,"");else scheduleRetry(reason);stopSelf();
    }

    private SleepAutomationSnapshot phase(SleepAutomationSnapshot s,String stage,String id,String reason,String mode){
        return new SleepAutomationSnapshot(stage,s.sleepDate,s.mediaUri,id,s.attempt,reason,System.currentTimeMillis(),mode);
    }
    private void failSequential(SleepAutomationStateStore states,SleepAutomationSnapshot s,String reason){
        states.save(phase(s,"FAILED",s.requestId,reason,s.mode));keepNotification=true;
        startForeground(840,notification("FAILED:"+reason));stopSelf();
    }
    private SleepAutomationApiClient.Job awaitStatus(SleepAutomationApiClient api,SleepAutomationSnapshot s,String[] secret){
        SleepAutomationApiClient.Job result=null;
        for(int i=0;i<15;i++){
            result=SleepAutomationApiClient.statusJob(api.status(s.requestId,s.sleepDate,secret[0],secret[1]),s.sleepDate);
            if(!"queued".equals(result.state)&&!"running".equals(result.state))break;
            if(i<14)try{Thread.sleep(1500);}catch(InterruptedException e){Thread.currentThread().interrupt();break;}
        }
        return result;
    }
    private void transferSequential(SleepAutomationSnapshot s,SleepAutomationStateStore states){
        String[] secret=new SleepAutomationSecretStore(this).read();
        if(secret==null){failSequential(states,s,"login_required");return;}
        SleepAutomationApiClient api=new SleepAutomationApiClient(getContentResolver());
        if("ocr".equals(s.mode)){
            if(s.requestId.isEmpty()){
                if("ready".equals(SleepAutomationApiClient.dateReportState(api.statusByDate(s.sleepDate,secret[0],secret[1]),s.sleepDate))){states.save(phase(s,"SUCCESS","","","report"));notifyFinalResult(true,"");stopSelf();return;}
                SleepAutomationApiClient.Job upload=SleepAutomationApiClient.uploadJob(api.upload(s.mediaUri,s.sleepDate,secret[0],secret[1],false));
                if(upload.requestId.isEmpty()){if(Arrays.asList("timeout","network_error","server_error").contains(upload.state)){scheduleRetry("ocr_pending");stopSelf();}else failSequential(states,s,upload.state);return;}
                s=phase(s,"POLLING",upload.requestId,"ocr_pending","ocr");states.save(s);
            }
            SleepAutomationApiClient.Job ocr=awaitStatus(api,s,secret);
            if(!"uploaded".equals(ocr.state)){if(Arrays.asList("queued","running","timeout","network_error","server_error").contains(ocr.state)){scheduleRetry("ocr_pending");stopSelf();}else failSequential(states,s,ocr.state);return;}
            s=phase(s,"UPLOADED",s.requestId,"","ocr_ready");states.save(s);
        }
        if("ocr_ready".equals(s.mode)){
            SleepAutomationApiClient.Job report=SleepAutomationApiClient.uploadJob(api.quickReport(s.sleepDate,secret[0],secret[1]));
            if(report.requestId.isEmpty()){if(Arrays.asList("timeout","network_error","server_error").contains(report.state)){scheduleRetry("report_request_pending");stopSelf();}else failSequential(states,s,report.state);return;}
            s=phase(s,"POLLING",report.requestId,"sleep_report_pending","report");states.save(s);
        }
        SleepAutomationApiClient.Job report=awaitStatus(api,s,secret);
        if(report.reportReady){states.save(phase(s,"SUCCESS",s.requestId,"","report"));notifyFinalResult(true,"");stopSelf();return;}
        if(Arrays.asList("queued","running","uploaded","done","reused","timeout","network_error","server_error").contains(report.state)){scheduleRetry("sleep_report_pending");stopSelf();return;}
        failSequential(states,s,report.state);
    }

    @Override public android.os.IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() {
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        worker.shutdownNow(); stopForeground(keepNotification?STOP_FOREGROUND_DETACH:STOP_FOREGROUND_REMOVE); super.onDestroy();
    }
}
