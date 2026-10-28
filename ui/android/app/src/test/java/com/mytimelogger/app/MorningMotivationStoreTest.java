package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class MorningMotivationStoreTest {
    @Test public void validatesAndUsesDeterministicOfflineFallback() {
        assertTrue(MorningMotivationStore.valid("2026-10-29", "今天先做好一件小事，行动会带你慢慢向前。"));
        assertFalse(MorningMotivationStore.valid("today", "今天先做好一件小事，行动会带你慢慢向前。"));
        assertFalse(MorningMotivationStore.valid("2026-10-29", "短句"));
        assertEquals(MorningMotivationStore.fallback("2026-10-29"), MorningMotivationStore.fallback("2026-10-29"));
        assertNotEquals(MorningMotivationStore.fallback("2026-10-29"), MorningMotivationStore.fallback("2026-10-30"));
    }
}
