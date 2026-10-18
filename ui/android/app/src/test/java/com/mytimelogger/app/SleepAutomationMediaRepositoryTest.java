package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;

public class SleepAutomationMediaRepositoryTest {
    @Test public void acceptsOnlyNewHuaweiJpegInsideWindow(){
        SleepAutomationMediaRepository.Baseline b=new SleepAutomationMediaRepository.Baseline(10,1000);
        assertTrue(SleepAutomationMediaRepository.matches(b,11,"sporthealth-1-20260929-230705.jpg","image/jpeg",1100,2000));
        assertFalse(SleepAutomationMediaRepository.matches(b,11,"camera.jpg","image/jpeg",1100,2000));
        assertFalse(SleepAutomationMediaRepository.matches(b,10,"sporthealth-1-20260929-230705.jpg","image/jpeg",1100,2000));
        assertFalse(SleepAutomationMediaRepository.matches(b,11,"sporthealth-1-20260929-230705.jpg","image/png",1100,2000));
        assertFalse(SleepAutomationMediaRepository.matches(b,11,"sporthealth-1-20260929-230705.jpg","image/jpeg",900,2000));
    }

    @Test public void requiresPermissionSizeStabilityAndUniqueness(){
        SleepAutomationMediaRepository r=new SleepAutomationMediaRepository(null);SleepAutomationMediaRepository.Candidate a=new SleepAutomationMediaRepository.Candidate(1,60000,"content://1"),b=new SleepAutomationMediaRepository.Candidate(2,60000,"content://2");
        assertEquals("media_permission_limited",r.select(Arrays.asList(a),false).code);
        assertEquals("media_not_found",r.select(Arrays.asList(new SleepAutomationMediaRepository.Candidate(3,100,"x")),true).code);
        assertEquals("media_ambiguous",r.select(Arrays.asList(a,b),true).code);
        assertEquals("media_not_stable",r.select(Arrays.asList(a),true).code);
        SleepAutomationMediaRepository.Result result=r.select(Arrays.asList(a),true);assertEquals("ok",result.code);assertEquals("content://1",result.candidate.uri);
    }
}
