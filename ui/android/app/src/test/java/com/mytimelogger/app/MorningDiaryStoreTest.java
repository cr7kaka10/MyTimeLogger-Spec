package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class MorningDiaryStoreTest {
    @Test public void classifiesOnlyNonBlankDiaryAsWritten(){
        assertEquals(MorningDiaryStore.WRITTEN,MorningDiaryStore.classify("晨间记录"));
        assertEquals(MorningDiaryStore.MISSING,MorningDiaryStore.classify("  "));
        assertEquals(MorningDiaryStore.MISSING,MorningDiaryStore.classify(null));
    }
}
