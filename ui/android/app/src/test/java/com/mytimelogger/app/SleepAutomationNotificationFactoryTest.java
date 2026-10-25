package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class SleepAutomationNotificationFactoryTest {
    @Test public void reportNotificationsNameBothFinalOutcomes(){
        assertEquals("今日睡眠报告生成成功",SleepAutomationNotificationFactory.resultTitle(true));
        assertTrue(SleepAutomationNotificationFactory.resultText(true,"").contains("今日睡眠报告已生成"));
        assertEquals("今日睡眠报告生成失败",SleepAutomationNotificationFactory.resultTitle(false));
        assertTrue(SleepAutomationNotificationFactory.resultText(false,"ocr_failed").contains("ocr_failed"));
    }

    @Test public void captureTestNotificationsDoNotClaimAReportWasGenerated(){
        assertTrue(SleepAutomationNotificationFactory.captureResultTitle(true).contains("图片采集成功"));
        assertTrue(SleepAutomationNotificationFactory.captureResultTitle(false).contains("图片采集失败"));
        assertTrue(SleepAutomationNotificationFactory.captureResultText(false,"capture_timeout").contains("图片未保存"));
    }
}
