package com.mytimelogger.app;

import android.content.ContentResolver;
import android.content.ContentUris;
import android.database.Cursor;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.provider.MediaStore;
import java.io.InputStream;
import java.util.*;
import java.util.regex.Pattern;

final class SleepAutomationMediaRepository {
    static final Pattern HUAWEI=Pattern.compile("sporthealth-.*-\\d{8}-\\d{6}\\.jpg",Pattern.CASE_INSENSITIVE);
    static final class Baseline { final long maxId,startedAt; Baseline(long id,long at){maxId=id;startedAt=at;} }
    private final ContentResolver resolver;
    private final Map<Long,Long> stableSizes=new HashMap<>();
    static final class Candidate { final long id,size,addedAt; final String uri; Candidate(long id,long size,String uri){this(id,size,uri,0);} Candidate(long id,long size,String uri,long addedAt){this.id=id;this.size=size;this.uri=uri;this.addedAt=addedAt;} }
    static final class Result { final String code; final Candidate candidate; Result(String code,Candidate c){this.code=code;candidate=c;} }
    static final class Inspection { final String code; final int width,height; Inspection(String code,int w,int h){this.code=code;width=w;height=h;} }
    SleepAutomationMediaRepository(ContentResolver resolver){this.resolver=resolver;}

    Baseline baseline(long now){
        long id=0;
        try(Cursor c=resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,new String[]{MediaStore.Images.Media._ID},null,null,MediaStore.Images.Media._ID+" DESC")){
            if(c!=null&&c.moveToFirst())id=c.getLong(0);
        }
        return new Baseline(id,now);
    }

    static boolean matches(Baseline b,long id,String name,String mime,long addedAt,long endAt,String date){
        return id>b.maxId&&name!=null&&HUAWEI.matcher(name).matches()&&name.contains("-"+date.replace("-","")+"-")&&"image/jpeg".equalsIgnoreCase(mime)&&addedAt>=b.startedAt-1000&&addedAt<=endAt;
    }
    Result select(List<Candidate> candidates,boolean fullPermission){
        if(!fullPermission)return new Result("media_permission_limited",null);List<Candidate> valid=new ArrayList<>();
        for(Candidate c:candidates)if(c.size>50L*1024L)valid.add(c);if(valid.isEmpty())return new Result("media_not_found",null);if(valid.size()>1)return new Result("media_ambiguous",null);
        Candidate c=valid.get(0);Long old=stableSizes.put(c.id,c.size);return old!=null&&old==c.size?new Result("ok",c):new Result("media_not_stable",null);
    }
    List<Candidate> candidates(Baseline b,long now,String date){
        List<Candidate> out=new ArrayList<>();String[] p={MediaStore.Images.Media._ID,MediaStore.Images.Media.DISPLAY_NAME,MediaStore.Images.Media.MIME_TYPE,MediaStore.Images.Media.SIZE,MediaStore.Images.Media.DATE_ADDED};
        try(Cursor c=resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,p,MediaStore.Images.Media._ID+">?",new String[]{String.valueOf(b.maxId)},null)){while(c!=null&&c.moveToNext()){long id=c.getLong(0),added=c.getLong(4)*1000L;if(matches(b,id,c.getString(1),c.getString(2),added,now,date))out.add(new Candidate(id,c.getLong(3),ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,id).toString(),added));}}
        return out;
    }
    static boolean completeJpeg(InputStream in) throws java.io.IOException {
        if(in==null||in.read()!=0xff||in.read()!=0xd8)return false;
        byte[] buf=new byte[8192];int previous=-1,last=-1;
        for(int n;(n=in.read(buf))!=-1;)for(int i=0;i<n;i++){previous=last;last=buf[i]&255;}
        return previous==0xff&&last==0xd9;
    }
    Inspection inspect(Candidate candidate){
        try(InputStream data=resolver.openInputStream(Uri.parse(candidate.uri))){if(!completeJpeg(data))return new Inspection("media_invalid_jpeg",0,0);}
        catch(Exception e){return new Inspection("media_unreadable",0,0);}
        try(InputStream data=resolver.openInputStream(Uri.parse(candidate.uri))){BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeStream(data,null,options);if(options.outWidth<480||options.outHeight<800)return new Inspection("media_invalid_dimensions",options.outWidth,options.outHeight);return new Inspection("ok",options.outWidth,options.outHeight);}
        catch(Exception e){return new Inspection("media_unreadable",0,0);}
    }
}
