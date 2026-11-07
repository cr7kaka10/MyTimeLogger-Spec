package com.mytimelogger.app;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.*;
import java.io.InputStream;

/** 在应用内预览本轮图片，避免依赖外部相册对超长图片的解码行为。 */
public final class SleepCapturePreviewActivity extends Activity {
    @Override protected void onCreate(Bundle state){
        super.onCreate(state);getWindow().setStatusBarColor(Color.WHITE);getWindow().setNavigationBarColor(Color.WHITE);
        SleepCaptureProbeStore probes=new SleepCaptureProbeStore(this);SleepCaptureProbeStore.Snapshot run=probes.load();
        if(run==null||!"SAVED".equals(run.stage)||run.uri.isEmpty()){error("没有可预览的本轮图片");return;}
        try(InputStream stream=getContentResolver().openInputStream(Uri.parse(run.uri))){
            BitmapFactory.Options options=new BitmapFactory.Options();options.inSampleSize=2;
            Bitmap bitmap=BitmapFactory.decodeStream(stream,null,options);
            if(bitmap==null){probes.finish(run,"FAILED","media_unreadable","",0,0,0);error("图片无法解码");return;}
            ScrollView page=new ScrollView(this);page.setBackgroundColor(Color.WHITE);
            ImageView image=new ImageView(this);image.setAdjustViewBounds(true);image.setImageBitmap(bitmap);
            image.setContentDescription("华为睡眠分享图片 "+run.date);
            page.addView(image,new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));setContentView(page);
        }catch(Exception e){probes.finish(run,"FAILED","media_unreadable","",0,0,0);error("图片无法打开");}
    }
    private void error(String message){TextView text=new TextView(this);text.setText(message);text.setTextSize(18);text.setPadding(32,32,32,32);setContentView(text);}
}
