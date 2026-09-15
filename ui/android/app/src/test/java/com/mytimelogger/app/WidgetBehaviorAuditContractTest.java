package com.mytimelogger.app;

import static org.junit.Assert.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.Test;

public class WidgetBehaviorAuditContractTest {
    @Test public void widgetCommandPersistsStandardBehaviorEvent() throws Exception {
        String repository = new String(Files.readAllBytes(Paths.get("src/main/java/com/mytimelogger/app/WidgetTimerRepository.java")), StandardCharsets.UTF_8);
        String receiver = new String(Files.readAllBytes(Paths.get("src/main/java/com/mytimelogger/app/WidgetTimerCommandReceiver.java")), StandardCharsets.UTF_8);
        assertTrue(repository.contains("behavior_event_outbox"));
        assertTrue(repository.contains("capacitor-android"));
        assertTrue(receiver.contains("recordBehavior(command.commandId, \"widget.timer_command\""));
    }
}
