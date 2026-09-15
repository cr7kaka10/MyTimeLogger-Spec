package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class SqliteBridgeDiagnosticsTest {
    @Test public void classifiesStableCategoriesWithoutLeakingMessages() {
        assertEquals("schema", SqliteConnection.errorCategory(new RuntimeException("no such column private-token")));
        assertEquals("constraint", SqliteConnection.errorCategory(new RuntimeException("constraint private-token")));
        assertEquals("storage", SqliteConnection.errorCategory(new RuntimeException("disk I/O private-token")));
        assertEquals("locked", SqliteConnection.errorCategory(new RuntimeException("database locked private-token")));
        assertEquals("unknown", SqliteConnection.errorCategory(new RuntimeException("private-token")));
        String json = SqliteBridge.operationFailure("transaction", 3,
                new RuntimeException("no such column private-token"), "sqlite_operation_failed");
        assertTrue(json.contains("\"operation\":\"transaction\""));
        assertTrue(json.contains("\"index\":3"));
        assertTrue(json.contains("\"error_category\":\"schema\""));
        assertFalse(json.contains("private-token"));
    }
}
