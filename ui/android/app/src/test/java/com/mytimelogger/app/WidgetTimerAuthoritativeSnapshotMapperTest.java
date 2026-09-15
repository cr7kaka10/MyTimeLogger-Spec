package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class WidgetTimerAuthoritativeSnapshotMapperTest {
    private static String response(String state,long base,long segmentSeconds){return "{\"status\":\"accepted\",\"state\":{"+
            "\"session_id\":\"s1\",\"revision\":2,\"state\":\""+state+"\",\"active\":"+(!"stopped".equals(state))+",\"category_id\":7,\"category_name\":\"状态切换\",\"started_at\":\"2026-08-24 10:00:00+08:00\",\"segment_started_at\":"+(segmentSeconds<0?"null":"\"2026-08-24 10:00:"+String.format("%02d",segmentSeconds)+"+08:00\"")+",\"active_elapsed_ms\":"+base+",\"timer_mode\":\"countup\",\"duration_ms\":0,\"pause_count\":0,\"server_time\":\"2026-08-24 10:00:10+08:00\"}}";}
    @Test public void mapsRunningUsingServerClockAndPausedWithoutGrowth(){WidgetTimerSnapshotParser.Parsed running=WidgetTimerSnapshotParser.parse(WidgetTimerAuthoritativeSnapshotMapper.map(WidgetTimerCurrentState.parse(response("running",1000,5)),99));assertNotNull(running);assertEquals(6000,running.snapshot.elapsedMs);assertEquals("状态切换",running.snapshot.categoryName);WidgetTimerSnapshotParser.Parsed paused=WidgetTimerSnapshotParser.parse(WidgetTimerAuthoritativeSnapshotMapper.map(WidgetTimerCurrentState.parse(response("paused",4000,-1)),100));assertTrue(paused.snapshot.paused);assertEquals(4000,paused.snapshot.elapsedMs);}
    @Test public void mapsStoppedAndRejectsInvalid(){WidgetTimerSnapshotParser.Parsed stopped=WidgetTimerSnapshotParser.parse(WidgetTimerAuthoritativeSnapshotMapper.map(WidgetTimerCurrentState.parse("{\"status\":\"stopped\",\"state\":null}"),123));assertEquals("stopped",stopped.snapshot.state);assertNull(WidgetTimerAuthoritativeSnapshotMapper.map(WidgetTimerCurrentState.parse("{}"),1));}
}
