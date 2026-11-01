package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.content.*;
import android.net.Uri;
import android.provider.MediaStore;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.OutputStream;
import java.text.SimpleDateFormat;
import java.util.*;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class SleepAutomationSequentialDeviceTest {
    @Test public void waitsForOcrBeforeRequestingAnalysis() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        SimpleDateFormat format=new SimpleDateFormat("yyyy-MM-dd",Locale.ROOT);format.setTimeZone(SleepAutomationScheduler.BEIJING);
        String date=format.format(new Date());
        ContentValues values=new ContentValues();values.put(MediaStore.Images.Media.DISPLAY_NAME,"sleep-sequential-test.jpg");values.put(MediaStore.Images.Media.MIME_TYPE,"image/jpeg");
        Uri image=context.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values);
        assertNotNull(image);
        try(SleepAutomationFakeServer server=new SleepAutomationFakeServer(date)){
            try(OutputStream out=context.getContentResolver().openOutputStream(image)){out.write(new byte[]{(byte)0xff,(byte)0xd8,(byte)0xff,(byte)0xd9});}
            new SleepAutomationSecretStore(context).save(server.url(),"test-token");
            SleepAutomationStateStore store=new SleepAutomationStateStore(context);
            store.save(new SleepAutomationSnapshot("MEDIA",date,image.toString(),"",1,"",System.currentTimeMillis(),"ocr"));
            context.startForegroundService(new Intent(context,SleepAutomationRunnerService.class).setAction(SleepAutomationRunnerService.TEST_ACTION));
            SleepAutomationSnapshot result=null;
            for(int i=0;i<100;i++){Thread.sleep(200);result=store.load(date);if(result!=null&&("SUCCESS".equals(result.stage)||"FAILED".equals(result.stage)))break;}
            assertNotNull(result);assertEquals(result.reason,"SUCCESS",result.stage);
            List<String> requests=server.requests;
            assertEquals(4,requests.size());
            assertTrue(requests.get(0).startsWith("/upload?analyze=false"));
            assertEquals("/status/ocr",requests.get(1));
            assertEquals("/generate_report",requests.get(2));
            assertEquals("/status/report",requests.get(3));
        }finally{context.getContentResolver().delete(image,null,null);new SleepAutomationSecretStore(context).clear();}
    }
}
