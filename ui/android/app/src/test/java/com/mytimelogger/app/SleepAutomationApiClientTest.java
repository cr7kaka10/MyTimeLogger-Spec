package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.file.*;
import org.junit.Test;

public class SleepAutomationApiClientTest {
    @Test public void uploadContractAndFailuresAreStable()throws Exception{
        assertEquals("https://host/upload?analyze=true&full=false&force=false&date=2026-10-01",SleepAutomationApiClient.endpoint("https://host/","2026-10-01"));
        assertEquals("https://host/upload?analyze=false&full=false&force=false&date=2026-10-01",SleepAutomationApiClient.endpoint("https://host/","2026-10-01",false));
        assertEquals("https://host/status_by_date/2026-10-01",SleepAutomationApiClient.statusByDateEndpoint("https://host/","2026-10-01"));
        assertEquals("https://host/generate_report",SleepAutomationApiClient.retryEndpoint("https://host/"));
        assertEquals("unauthorized",SleepAutomationApiClient.classify(401));assertEquals("server_error",SleepAutomationApiClient.classify(503));assertEquals("ok",SleepAutomationApiClient.classify(200));assertTrue(SleepAutomationApiClient.tooLarge(15L*1024L*1024L+1));
        String s=new String(Files.readAllBytes(Paths.get("src/main/java/com/mytimelogger/app/SleepAutomationApiClient.java")),"UTF-8");assertTrue(s.contains("openInputStream")&&s.contains("setChunkedStreamingMode")&&s.contains("Bearer "));assertFalse(s.contains("readAllBytes"));
    }
    @Test public void requestIdAndStatusMappingRejectUnknownOrWrongDate(){
        SleepAutomationApiClient.Job upload=SleepAutomationApiClient.uploadJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"reused\":true}"));assertEquals("reused",upload.state);assertEquals("abc",upload.requestId);
        assertEquals("running",SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"running\",\"date\":\"2026-10-01\"}"),"2026-10-01").state);
        assertEquals("uploaded",SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"uploaded\",\"date\":\"2026-10-01\"}"),"2026-10-01").state);
        SleepAutomationApiClient.Job done=SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"done\",\"date\":\"2026-10-01\",\"result\":{\"report_status\":2,\"full_report_state\":\"generated\",\"analysis_report\":\"report\"}}"),"2026-10-01");assertTrue(done.reportReady);
        assertFalse(SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"done\",\"date\":\"2026-10-01\",\"result\":{\"report_status\":1}}"),"2026-10-01").reportReady);
        assertTrue(SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"done\",\"date\":\"2026-10-01\",\"result\":{\"report_status\":1,\"analysis_report\":\"sleep report\"}}"),"2026-10-01").reportReady);
        assertEquals("ready",SleepAutomationApiClient.dateReportState(new SleepAutomationApiClient.Result("ok","{\"status\":\"error\",\"date\":\"2026-10-01\",\"result\":{\"report_status\":1,\"analysis_report\":\"saved report\"}}"),"2026-10-01"));
        assertEquals("missing",SleepAutomationApiClient.dateReportState(new SleepAutomationApiClient.Result("http_error","{\"detail\":\"date not found\"}"),"2026-10-01"));
        assertEquals("unknown",SleepAutomationApiClient.dateReportState(new SleepAutomationApiClient.Result("network_error",""),"2026-10-01"));
        assertEquals("date_mismatch",SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"done\",\"date\":\"2026-09-30\"}"),"2026-10-01").state);
        assertEquals("protocol_error",SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"mystery\"}"),"2026-10-01").state);
        assertEquals("vision_model_unconfigured",SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"error\",\"error\":\"当前用户未配置视觉大模型\"}"),"2026-10-01").state);
        assertEquals("ocr_failed",SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"error\",\"error\":\"OCR failed\"}"),"2026-10-01").state);
        assertEquals("report_failed",SleepAutomationApiClient.statusJob(new SleepAutomationApiClient.Result("ok","{\"request_id\":\"abc\",\"status\":\"error\",\"error\":\"secret-value\"}"),"2026-10-01").state);
    }
}
