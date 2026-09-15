package com.mytimelogger.app;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertThrows;

import java.util.Collections;
import org.junit.Test;

public class SqliteValueCodecTest {
    private static Object roundTrip(Object value) {
        return SqliteValueCodec.decode(SqliteValueCodec.encode(value));
    }

    @Test
    public void supportedValuesRoundTrip() {
        assertNull(roundTrip(null));
        assertEquals(Integer.valueOf(7), roundTrip(7));
        assertEquals(Long.valueOf(900719925474099L), roundTrip(900719925474099L));
        assertEquals(Float.valueOf(1.25f), roundTrip(1.25f));
        assertEquals(Double.valueOf(-2.5d), roundTrip(-2.5d));
        assertEquals("中文🙂SQLite", roundTrip("中文🙂SQLite"));
        assertArrayEquals(new byte[] {0, 1, -1, 127}, (byte[]) roundTrip(new byte[] {0, 1, -1, 127}));
    }

    @Test
    public void invalidValuesAreRejected() {
        IllegalArgumentException unsupported = assertThrows(
            IllegalArgumentException.class, () -> SqliteValueCodec.encode(Boolean.TRUE));
        assertEquals("unsupported_sqlite_value", unsupported.getMessage());
        IllegalArgumentException invalidBlob = assertThrows(
            IllegalArgumentException.class,
            () -> SqliteValueCodec.decode(Collections.singletonMap("$blob", "0xz")));
        assertEquals("invalid_blob_value", invalidBlob.getMessage());
    }
}
