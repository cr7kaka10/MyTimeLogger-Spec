package com.mytimelogger.app;
import static org.junit.Assert.*;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.net.Uri;
import android.provider.MediaStore;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.OutputStream;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class SleepCaptureGalleryExporterDeviceTest {
    @Test public void exportsReadableImageOnceIntoPublicAlbum() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        ContentResolver resolver=context.getContentResolver();
        ContentValues sourceValues=new ContentValues();
        sourceValues.put(MediaStore.Images.Media.DISPLAY_NAME,"mtl-gallery-source.jpg");
        sourceValues.put(MediaStore.Images.Media.MIME_TYPE,"image/jpeg");
        sourceValues.put(MediaStore.Images.Media.RELATIVE_PATH,"Pictures/MyTimeLoggerTest/");
        Uri source=resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,sourceValues);
        assertNotNull(source);
        Bitmap bitmap=Bitmap.createBitmap(600,600,Bitmap.Config.ARGB_8888);
        for(int y=0;y<600;y++)for(int x=0;x<600;x++)bitmap.setPixel(x,y,0xff000000|((x*31337+y*7919)&0xffffff));
        try(OutputStream output=resolver.openOutputStream(source)){assertNotNull(output);assertTrue(bitmap.compress(Bitmap.CompressFormat.JPEG,95,output));}
        bitmap.recycle();
        String day="2026-11-01",runId="gallery-test-"+System.currentTimeMillis();
        try(Cursor old=resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,new String[]{MediaStore.Images.Media._ID},
                MediaStore.Images.Media.DISPLAY_NAME+" LIKE ?",new String[]{"MyTimeLogger_Sleep_"+day+"_gallerytest%"},null)){
            while(old!=null&&old.moveToNext())resolver.delete(Uri.withAppendedPath(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,old.getString(0)),null,null);}
        SleepCaptureProbeStore.Snapshot probe=new SleepCaptureProbeStore.Snapshot(runId,day,"SAVED","",source.toString(),1,2,600,600);
        String name="MyTimeLogger_Sleep_"+day+"_"+runId.replaceAll("[^A-Za-z0-9]","")+".jpg";
        Uri target=null;
        try {
            assertEquals("saved",SleepCaptureGalleryExporter.export(context,probe,day));
            assertEquals("already_saved",SleepCaptureGalleryExporter.export(context,probe,day));
            try(Cursor rows=resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    new String[]{MediaStore.Images.Media._ID,MediaStore.Images.Media.SIZE},
                    MediaStore.Images.Media.DISPLAY_NAME+"=? AND "+MediaStore.Images.Media.RELATIVE_PATH+"=?",
                    new String[]{name,SleepCaptureGalleryExporter.ALBUM},null)){
                assertNotNull(rows);assertTrue(rows.moveToFirst());assertTrue(rows.getLong(1)>50_000);
                target=Uri.withAppendedPath(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,rows.getString(0));assertFalse(rows.moveToNext());
            }
        } finally { if(target!=null)resolver.delete(target,null,null);resolver.delete(source,null,null); }
    }
}
