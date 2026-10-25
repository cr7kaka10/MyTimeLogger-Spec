package com.mytimelogger.app;

import android.content.Context;
import android.content.SharedPreferences;
import com.google.gson.Gson;
import java.util.UUID;

/** 图片采集验收状态，独立于每日上传/报告任务。 */
final class SleepCaptureProbeStore {
    static final class Snapshot {
        final String runId, date, stage, reason, uri;
        final long startedAt, savedAt;
        final int width, height;
        Snapshot(String id,String day,String step,String why,String image,long started,long saved,int w,int h){
            runId=id;date=day;stage=step;reason=why;uri=image;startedAt=started;savedAt=saved;width=w;height=h;
        }
    }
    private static final Gson JSON=new Gson();
    private final SharedPreferences state,owner;
    SleepCaptureProbeStore(Context context){
        state=context.getSharedPreferences("sleep-capture-probe",Context.MODE_PRIVATE);
        owner=context.getSharedPreferences("sleep-automation",Context.MODE_PRIVATE);
    }
    private String key(){return "probe:"+owner.getString("meta:owner","");}
    synchronized Snapshot load(){try{return JSON.fromJson(state.getString(key(),null),Snapshot.class);}catch(Exception ignored){return null;}}
    synchronized Snapshot start(String date){Snapshot s=new Snapshot(UUID.randomUUID().toString(),date,"RUNNING","","",System.currentTimeMillis(),0,0,0);save(s);return s;}
    synchronized void finish(Snapshot run,String stage,String reason,String uri,long savedAt,int width,int height){
        Snapshot current=load();if(current==null||!current.runId.equals(run.runId))return;
        save(new Snapshot(run.runId,run.date,stage,reason,uri,run.startedAt,savedAt,width,height));
    }
    private void save(Snapshot value){state.edit().putString(key(),JSON.toJson(value)).commit();}
}
