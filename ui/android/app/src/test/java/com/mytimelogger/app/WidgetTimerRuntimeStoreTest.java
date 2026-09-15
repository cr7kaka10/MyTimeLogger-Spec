package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class WidgetTimerRuntimeStoreTest {
    private static final class Memory implements WidgetTimerRuntimeStore.Backend {
        String value; public String read() { return value; }
        public boolean write(String next) { value = next; return true; }
        public void clear() { value = null; }
    }
    private static final class FakeCrypto implements WidgetTimerRuntimeStore.Crypto {
        boolean cleared; public String encrypt(String value) { return "cipher:" + new StringBuilder(value).reverse(); }
        public String decrypt(String value) { if (!value.startsWith("cipher:")) throw new IllegalArgumentException(); return new StringBuilder(value.substring(7)).reverse().toString(); }
        public void clear() { cleared = true; }
    }
    private static String config(String token, String user, long generation) {
        return "{\"serverUrl\":\"https://example.test/\",\"authToken\":\"" + token
                + "\",\"deviceId\":\"device-1\",\"verifiedUserId\":\"" + user + "\",\"generation\":" + generation + "}";
    }
    @Test public void encryptsRoundTripsAndRejectsCorruption() {
        Memory disk = new Memory(); FakeCrypto crypto = new FakeCrypto(); WidgetTimerRuntimeStore store = new WidgetTimerRuntimeStore(disk, crypto);
        assertTrue(store.configure(config("test-a", "1", 1))); assertFalse(disk.value.contains("test-a"));
        WidgetTimerRuntimeStore.Config value = store.read(); assertNotNull(value); assertEquals("test-a", value.authToken); assertEquals("https://example.test", value.serverUrl);
        disk.value = "2." + disk.value.substring(disk.value.indexOf('.') + 1); assertNull(store.read());
        disk.value = "broken"; assertNull(store.read());
    }
    @Test public void atomicallyReplacesAccountAndClearsEverything() {
        Memory disk = new Memory(); FakeCrypto crypto = new FakeCrypto(); WidgetTimerRuntimeStore store = new WidgetTimerRuntimeStore(disk, crypto);
        assertTrue(store.configure(config("test-a", "1", 1))); assertTrue(store.configure(config("test-b", "2", 2)));
        assertEquals("2", store.read().verifiedUserId); assertFalse(disk.value.contains("test-a"));
        assertFalse(store.configure("{\"serverUrl\":\"https://example.test\"}")); assertEquals("2", store.read().verifiedUserId);
        store.clear(); assertNull(store.read()); assertNull(disk.value); assertTrue(crypto.cleared);
    }
}
