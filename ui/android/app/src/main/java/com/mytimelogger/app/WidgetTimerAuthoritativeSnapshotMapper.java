package com.mytimelogger.app;

import com.google.gson.Gson;

public final class WidgetTimerAuthoritativeSnapshotMapper {
    public static String map(WidgetTimerCurrentState state,long capturedAtEpochMs){
        if(state==null)return null;
        WidgetTimerEngine.Snapshot snapshot;
        if(!state.active)snapshot=WidgetTimerEngine.Snapshot.stopped(capturedAtEpochMs);
        else{
            long elapsed=state.activeElapsedMs;
            if("running".equals(state.state)&&state.segmentStartedAtEpochMs>0)
                elapsed+=Math.max(0,state.serverTimeEpochMs-state.segmentStartedAtEpochMs);
            snapshot=new WidgetTimerEngine.Snapshot("countup_studying","paused".equals(state.state),state.categoryId,
                    state.categoryName,capturedAtEpochMs,elapsed,state.startedAtEpochMs);
        }
        String json=new Gson().toJson(snapshot.toCompatibleMap());
        return WidgetTimerSnapshotParser.parse(json)==null?null:json;
    }
    private WidgetTimerAuthoritativeSnapshotMapper(){}
}
