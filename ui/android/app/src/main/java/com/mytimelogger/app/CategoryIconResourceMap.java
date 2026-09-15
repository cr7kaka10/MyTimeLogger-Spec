package com.mytimelogger.app;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import java.io.IOException;

public final class CategoryIconResourceMap {
    private static final int SAFE_COLOR = 0xFF5E81AC;

    static String assetPathFor(String key) {
        String name = key != null && key.startsWith("atm:") ? key.substring(4) : "";
        return name.matches("[a-z0-9_]+") ? "public/icons/atm/" + name + ".png" : null;
    }

    static Bitmap bitmapFor(Context context, String key) {
        String path = assetPathFor(key);
        if (path == null) return null;
        try {
            Bitmap source = BitmapFactory.decodeStream(context.getAssets().open(path));
            if (source == null) return null;
            return Bitmap.createScaledBitmap(source, 96, 96, true);
        } catch (IOException unavailable) { return null; }
    }

    static boolean shouldTint(String key, boolean disabled) {
        if (disabled) return true;
        String name = key != null && key.startsWith("atm:") ? key.substring(4) : "";
        return !(name.startsWith("flat_") || name.startsWith("swift_"));
    }

    static int tintFor(String savedColor, boolean disabled, int disabledGrey) {
        if (disabled) return disabledGrey;
        if (savedColor == null || !savedColor.matches("#[0-9A-Fa-f]{6}")) return SAFE_COLOR;
        return (int) (0xFF000000L | Long.parseLong(savedColor.substring(1), 16));
    }

    private CategoryIconResourceMap() {}
}
