package com.mytimelogger.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class SqliteBridgeTest {
    private static final String NOT_READY = "{\"ok\":false,\"error\":\"sqlite_not_initialized\"}";
    private Context context;
    private String name;
    private SqliteBridge bridge;

    @Before public void setUp() {
        context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        name = "bridge-contract.db";
        context.deleteDatabase(name);
        bridge = new SqliteBridge(context);
    }

    @After public void tearDown() { bridge.close(); context.deleteDatabase(name); }

    @Test public void initializesAndRejectsCallsBeforeOpen() {
        assertEquals(NOT_READY, bridge.execute("CREATE TABLE hidden(value TEXT)", "[]"));
        assertEquals(NOT_READY, bridge.query("SELECT * FROM hidden", "[]"));
        assertEquals(NOT_READY, bridge.transaction("[]"));
        assertEquals("{\"ok\":false,\"error\":\"invalid_bridge_arguments\"}", bridge.open("../private.db"));
        assertEquals("{\"ok\":true}", bridge.open(name));
        assertEquals("{\"ok\":true}", bridge.execute("CREATE TABLE sample(value TEXT)", "[]"));
        assertEquals("{\"ok\":true,\"rows\":[]}", bridge.query("SELECT * FROM sample", "[]"));
    }

    @Test public void transactionCommitsOrRollsBackWithoutLeakingParameters() {
        bridge.open(name);
        bridge.execute("CREATE TABLE sample(value TEXT NOT NULL)", "[]");
        assertEquals("{\"ok\":true}", bridge.transaction("[{\"sql\":\"INSERT INTO sample VALUES(?)\",\"params\":[\"one\"]},{\"sql\":\"INSERT INTO sample VALUES(?)\",\"params\":[\"two\"]}]"));
        assertEquals("{\"ok\":true,\"rows\":[{\"count\":2}]}", bridge.query("SELECT COUNT(*) AS count FROM sample", "[]"));
        String secret = "private-token-456";
        String failed = bridge.transaction("[{\"sql\":\"INSERT INTO sample VALUES(?)\",\"params\":[\"three\"]},{\"sql\":\"INSERT INTO sample VALUES(?)\",\"params\":[null,\"" + secret + "\"]}]");
        assertTrue(failed.contains("\"error\":\"sqlite_operation_failed\""));
        assertTrue(failed.contains("\"operation\":\"transaction\""));
        assertTrue(failed.contains("\"index\":1"));
        assertTrue(failed.contains("\"error_category\":"));
        assertFalse(failed.contains(secret));
        assertEquals("{\"ok\":true,\"rows\":[{\"count\":2}]}", bridge.query("SELECT COUNT(*) AS count FROM sample", "[]"));
    }

    @Test public void mapsInvalidArgumentsAndRedactsOperationFailure() {
        bridge.open(name);
        assertEquals("{\"ok\":false,\"error\":\"invalid_bridge_arguments\"}", bridge.execute("SELECT ?", "{\"value\":1}"));
        String sql = "INSERT INTO missing_private_table VALUES(?)";
        String secret = "private-token-123";
        String result = bridge.execute(sql, "[\"" + secret + "\"]");
        assertEquals("{\"ok\":false,\"error\":\"sqlite_operation_failed\",\"operation\":\"execute\",\"error_category\":\"schema\"}", result);
        assertFalse(result.contains(sql));
        assertFalse(result.contains(secret));
        assertFalse(result.contains(context.getDatabasePath(name).getAbsolutePath()));
    }
}
