package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class CategoryIconResourceMapTest {
    @Test public void allDefaultKeysResolveToAuthoritativePngAndUnknownUsesFallback() {
        String[] keys = {"atm:cat_96", "atm:cat_85", "atm:cat_158", "atm:fs_010",
                "atm:st_024", "atm:ec_045", "atm:fam_021", "atm:cat_116",
                "atm:cat_205", "atm:hpcd_034", "atm:sp_068", "atm:cat_79",
                "atm:cat_5", "atm:fam_008", "atm:hpcd_041"};
        for (int index = 0; index < keys.length; index++)
            assertEquals(keys[index], "public/icons/atm/" + keys[index].substring(4) + ".png",
                    CategoryIconResourceMap.assetPathFor(keys[index]));
        assertNull(CategoryIconResourceMap.assetPathFor("file://bad"));
        assertTrue(CategoryIconResourceMap.shouldTint("atm:cat_96", false));
        assertFalse(CategoryIconResourceMap.shouldTint("atm:flat_001", false));
        assertFalse(CategoryIconResourceMap.shouldTint("atm:swift_001", false));
        assertTrue(CategoryIconResourceMap.shouldTint("atm:flat_001", true));
    }

    @Test public void savedColorIsNormalizedAndDisabledAlwaysGrey() {
        assertEquals(0xFF123456, CategoryIconResourceMap.tintFor("#123456", false, 0xFF888888));
        assertEquals(0xFF5E81AC, CategoryIconResourceMap.tintFor("bad", false, 0xFF888888));
        assertEquals(0xFF888888, CategoryIconResourceMap.tintFor("#123456", true, 0xFF888888));
    }
}
