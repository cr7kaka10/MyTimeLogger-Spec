package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.regex.Pattern;
import org.junit.Test;

public class TimerWidgetIconLicenseContractTest {
    @Test public void everyPrivateVectorRecordsSourceVersionAndRestriction() throws Exception {
        String notice = new String(Files.readAllBytes(
                Paths.get("..", "..", "THIRD_PARTY_NOTICES.md")), StandardCharsets.UTF_8);
        String[] resources = {"ic_timer_cat_96", "ic_timer_cat_85", "ic_timer_cat_158",
                "ic_timer_fs_010", "ic_timer_st_024", "ic_timer_ec_045",
                "ic_timer_fam_021", "ic_timer_cat_116", "ic_timer_cat_205",
                "ic_timer_hpcd_034", "ic_timer_sp_068", "ic_timer_cat_79",
                "ic_timer_cat_5", "ic_timer_fam_008", "ic_timer_hpcd_041"};
        for (String resource : resources) {
            String row = "(?m)^\\|[^\\n]*" + resource
                    + "[^\\n]*app-beta-1-6-0-52\\.apk"
                    + "[^\\n]*private-use-only; no redistribution[^\\n]*$";
            assertTrue(resource, Pattern.compile(row).matcher(notice).find());
        }
        assertTrue(notice.contains("MUST NOT be pushed to a public repository"));
        assertTrue(notice.contains("MUST NOT be distributed to third parties"));
    }
}
