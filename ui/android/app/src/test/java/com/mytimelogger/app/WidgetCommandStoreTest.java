package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.Test;

public class WidgetCommandStoreTest {
    @Test public void claimAndAppliedResultAreIdempotentAndBounded() {
        WidgetCommandStore store = new WidgetCommandStore(2);
        assertTrue(store.claim("one").newlyClaimed);
        store.markApplied("one", "applied");
        WidgetCommandStore.Entry duplicate = store.claim("one");
        assertFalse(duplicate.newlyClaimed);
        assertEquals("applied", duplicate.result);
        assertTrue(duplicate.applied);
        store.claim("two"); store.claim("three");
        assertEquals(2, store.size());
        assertNull(store.get("one"));
    }

    @Test public void concurrentClaimHasOneWinner() throws Exception {
        WidgetCommandStore store = new WidgetCommandStore(8);
        ExecutorService pool = Executors.newFixedThreadPool(8);
        List<Future<WidgetCommandStore.Entry>> futures = new ArrayList<>();
        for (int index = 0; index < 16; index++) futures.add(pool.submit(() -> store.claim("same")));
        int winners = 0;
        for (Future<WidgetCommandStore.Entry> future : futures) if (future.get().newlyClaimed) winners++;
        pool.shutdownNow();
        assertEquals(1, winners);
        assertEquals(1, store.size());
    }

    @Test public void persistsPendingUnknownAndHeadlessAcceptedDistinctly() {
        Map<String,String> disk=new HashMap<>(); WidgetTimerPreferences.Backend backend=new WidgetTimerPreferences.Backend(){public String get(String key){return disk.get(key);}public void put(String key,String value){disk.put(key,value);}};
        WidgetCommandStore store=new WidgetCommandStore(backend,8); store.claim("pending"); store.mark("pending","unknown",false); store.claim("done"); store.mark("done","headless-applied",true);
        WidgetCommandStore restored=new WidgetCommandStore(backend,8); assertFalse(restored.claim("pending").applied); assertEquals("unknown",restored.get("pending").result); assertTrue(restored.claim("done").applied); assertEquals("headless-applied",restored.get("done").result);
    }
}
