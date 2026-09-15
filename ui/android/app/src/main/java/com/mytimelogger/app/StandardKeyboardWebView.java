package com.mytimelogger.app;

import android.content.Context;
import android.os.Build;
import android.text.InputType;
import android.util.AttributeSet;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import com.getcapacitor.CapacitorWebView;

public final class StandardKeyboardWebView extends CapacitorWebView {
    static final boolean SHOW_SOFT_INPUT_ON_FOCUS = true;

    public StandardKeyboardWebView(Context context, AttributeSet attributes) {
        super(context, attributes);
        setFocusable(true);
        setFocusableInTouchMode(SHOW_SOFT_INPUT_ON_FOCUS);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            setAutoHandwritingEnabled(false);
        }
    }

    @Override public InputConnection onCreateInputConnection(EditorInfo attributes) {
        InputConnection connection = super.onCreateInputConnection(attributes);
        attributes.inputType = standardKeyboardInputType(attributes.inputType);
        return connection;
    }

    static int standardKeyboardInputType(int inputType) {
        int inputClass = inputType & InputType.TYPE_MASK_CLASS;
        if (inputClass != InputType.TYPE_CLASS_TEXT) {
            return inputType;
        }
        return (inputType & ~InputType.TYPE_MASK_VARIATION)
            | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD;
    }
}
