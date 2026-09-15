package com.mytimelogger.app;

import java.util.Collections;
import java.util.Map;

final class SqliteValueCodec {
    private static final String BLOB_KEY = "$blob";
    private static final char[] HEX = "0123456789abcdef".toCharArray();

    private SqliteValueCodec() {}

    static Object encode(Object value) {
        if (value == null || value instanceof Number || value instanceof String) return value;
        if (value instanceof byte[]) return Collections.singletonMap(BLOB_KEY, toHex((byte[]) value));
        throw new IllegalArgumentException("unsupported_sqlite_value");
    }

    static Object decode(Object value) {
        if (value == null || value instanceof Number || value instanceof String) return value;
        if (value instanceof Map<?, ?>) {
            Object encoded = ((Map<?, ?>) value).get(BLOB_KEY);
            if (encoded instanceof String) return fromHex((String) encoded);
        }
        throw new IllegalArgumentException("unsupported_sqlite_value");
    }

    private static String toHex(byte[] value) {
        char[] result = new char[value.length * 2];
        for (int i = 0; i < value.length; i++) {
            int next = value[i] & 0xff;
            result[i * 2] = HEX[next >>> 4]; result[i * 2 + 1] = HEX[next & 0x0f];
        }
        return new String(result);
    }

    private static byte[] fromHex(String value) {
        if ((value.length() & 1) != 0) throw new IllegalArgumentException("invalid_blob_value");
        byte[] result = new byte[value.length() / 2];
        for (int i = 0; i < result.length; i++) {
            int high = Character.digit(value.charAt(i * 2), 16);
            int low = Character.digit(value.charAt(i * 2 + 1), 16);
            if (high < 0 || low < 0) throw new IllegalArgumentException("invalid_blob_value");
            result[i] = (byte) ((high << 4) | low);
        }
        return result;
    }
}
