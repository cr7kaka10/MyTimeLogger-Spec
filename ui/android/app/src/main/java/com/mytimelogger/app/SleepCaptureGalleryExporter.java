package com.mytimelogger.app;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.provider.MediaStore;
import java.io.InputStream;
import java.io.OutputStream;
final class SleepCaptureGalleryExporter {
    static final String ALBUM = "Pictures/MyTimeLogger/";
    static String export(Context context, SleepCaptureProbeStore.Snapshot probe, String today) {
        if (Build.VERSION.SDK_INT < 29) return "unsupported_android";
        if (probe == null || !"SAVED".equals(probe.stage) || !today.equals(probe.date)) return "today_capture_required";
        ContentResolver resolver = context.getContentResolver();
        Uri source;
        try { source = Uri.parse(probe.uri); } catch (Exception error) { return "media_unreadable"; }
        String name = "MyTimeLogger_Sleep_" + today + "_" + probe.runId.replaceAll("[^A-Za-z0-9]", "") + ".jpg";
        Uri images = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
        try (Cursor found = resolver.query(images, new String[]{MediaStore.Images.Media._ID, MediaStore.Images.Media.SIZE},
                MediaStore.Images.Media.DISPLAY_NAME + "=? AND " + MediaStore.Images.Media.RELATIVE_PATH + "=?",
                new String[]{name, ALBUM}, null)) {
            if (found != null && found.moveToFirst() && found.getLong(1) > 0) return "already_saved";
        } catch (Exception error) { return "gallery_query_failed"; }
        ContentValues values = new ContentValues();
        values.put(MediaStore.Images.Media.DISPLAY_NAME, name);
        values.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
        values.put(MediaStore.Images.Media.RELATIVE_PATH, ALBUM);
        values.put(MediaStore.Images.Media.IS_PENDING, 1);
        Uri target = null;
        try (InputStream in = resolver.openInputStream(source)) {
            if (in == null) return "media_unreadable";
            target = resolver.insert(images, values);
            if (target == null) return "gallery_write_failed";
            try (OutputStream out = resolver.openOutputStream(target)) {
                if (out == null) throw new IllegalStateException("gallery_output_missing");
                byte[] bytes = new byte[8192]; int read; long size = 0;
                while ((read = in.read(bytes)) != -1) { out.write(bytes, 0, read); size += read; }
                if (size < 50L * 1024L) throw new IllegalStateException("image_too_small");
            }
            ContentValues ready = new ContentValues(); ready.put(MediaStore.Images.Media.IS_PENDING, 0);
            resolver.update(target, ready, null, null);
            return "saved";
        } catch (Exception error) {
            if (target == null) return "media_unreadable";
            try { resolver.delete(target, null, null); } catch (Exception ignored) { }
            return "gallery_write_failed";
        }
    }
}
