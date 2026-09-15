package com.mytimelogger.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import android.text.InputType;
import org.junit.Test;

public class StandardKeyboardWebViewContractTest {
    @Test public void focusedWebViewRequestsSystemSoftInput() {
        assertTrue(StandardKeyboardWebView.SHOW_SOFT_INPUT_ON_FOCUS);
    }

    @Test public void allTextVariationsUseStandardKeyboardWithoutLosingFlags() {
        int[] textInputs = {
            InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_NORMAL,
            InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS,
            InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI,
            InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_LONG_MESSAGE
                | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS,
            InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
        };
        for (int original : textInputs) {
            int expected = (original & ~InputType.TYPE_MASK_VARIATION)
                | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD;
            assertEquals(expected, StandardKeyboardWebView.standardKeyboardInputType(original));
        }
    }

    @Test public void numericAndPhoneInputsRemainUnchanged() {
        int number = InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL;
        int phone = InputType.TYPE_CLASS_PHONE;

        assertEquals(number, StandardKeyboardWebView.standardKeyboardInputType(number));
        assertEquals(phone, StandardKeyboardWebView.standardKeyboardInputType(phone));
    }
}
