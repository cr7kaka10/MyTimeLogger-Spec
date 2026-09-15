package com.mytimelogger.app;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertThrows;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class SqliteConnectionTest {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    private final String name = "sqlite-connection-test.db";

    @After public void cleanup() { context.deleteDatabase(name); }

    @Test public void reopenBindAndQueryTypedRowsInOrder() {
        context.deleteDatabase(name);
        SqliteConnection first = new SqliteConnection(context, name);
        first.open();
        first.execute("CREATE TABLE sample(id INTEGER, label TEXT, optional TEXT, payload BLOB, score REAL)", Collections.emptyList());
        first.execute("INSERT INTO sample VALUES(?,?,?,?,?)", Arrays.asList(1L, "中文🙂", null, new byte[] {0, -1}, 1.5d));
        first.execute("INSERT INTO sample VALUES(?,?,?,?,?)", Arrays.asList(2L, "second", "value", new byte[] {2}, 2.5d));
        first.close();

        SqliteConnection reopened = new SqliteConnection(context, name);
        reopened.open();
        List<Map<String, Object>> rows = reopened.query("SELECT id,label,optional,payload,score FROM sample ORDER BY id", Collections.emptyList());
        assertEquals(2, rows.size());
        assertEquals(Arrays.asList("id", "label", "optional", "payload", "score"), new ArrayList<>(rows.get(0).keySet()));
        assertEquals(Long.valueOf(1), rows.get(0).get("id"));
        assertEquals("中文🙂", rows.get(0).get("label"));
        assertNull(rows.get(0).get("optional"));
        assertArrayEquals(new byte[] {0, -1}, (byte[]) SqliteValueCodec.decode(rows.get(0).get("payload")));
        assertEquals(Double.valueOf(1.5d), rows.get(0).get("score"));
        assertEquals(Long.valueOf(2), reopened.query("SELECT id FROM sample WHERE label=?", Collections.singletonList("second")).get(0).get("id"));
        reopened.close();
    }

    @Test public void transactionCommitsRollsBackAndRejectsNesting() {
        context.deleteDatabase(name);
        SqliteConnection connection = new SqliteConnection(context, name);
        connection.open();
        connection.execute("CREATE TABLE tx(id INTEGER)", Collections.emptyList());
        connection.transaction(() -> connection.execute("INSERT INTO tx VALUES(?)", Collections.singletonList(1L)));
        RuntimeException failure = assertThrows(RuntimeException.class, () -> connection.transaction(() -> {
            connection.execute("INSERT INTO tx VALUES(?)", Collections.singletonList(2L));
            throw new RuntimeException("force_rollback");
        }));
        assertEquals("force_rollback", failure.getMessage());
        connection.transaction(() -> {
            IllegalStateException nested = assertThrows(IllegalStateException.class, () -> connection.transaction(() -> {}));
            assertEquals("nested_transaction_not_supported", nested.getMessage());
        });
        List<Map<String, Object>> rows = connection.query("SELECT id FROM tx ORDER BY id", Collections.emptyList());
        assertEquals(1, rows.size());
        assertEquals(Long.valueOf(1), rows.get(0).get("id"));
        connection.close();
    }
}
