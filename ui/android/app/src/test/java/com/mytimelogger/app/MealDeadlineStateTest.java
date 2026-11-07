package com.mytimelogger.app;

import static org.junit.Assert.*;
import java.util.Collections;
import org.junit.Test;

public class MealDeadlineStateTest {
    @Test public void onlyExplicitPendingMayPrompt() {
        assertFalse(MealDeadlineState.shouldRemind(Collections.emptyList()));
        assertTrue(MealDeadlineState.shouldRemind(Collections.singletonList(Collections.singletonMap("status", "pending"))));
        assertFalse(MealDeadlineState.shouldRemind(Collections.singletonList(Collections.singletonMap("status", "completed"))));
        assertFalse(MealDeadlineState.shouldRemind(Collections.singletonList(Collections.singletonMap("status", "failed"))));
    }
}
