package com.mytimelogger.app;

import android.content.ContentResolver;
import android.content.res.AssetFileDescriptor;
import android.net.Uri;
import java.io.*;
import java.net.*;
import com.google.gson.*;

final class SleepAutomationApiClient {
    static final long MAX=15L*1024L*1024L; private final ContentResolver resolver;
    static final class Result { final String code,body; Result(String c,String b){code=c;body=b;} }
    static final class Job { final String state,requestId; final boolean reportReady; Job(String s,String id){this(s,id,false);} Job(String s,String id,boolean ready){state=s;requestId=id;reportReady=ready;} }
    SleepAutomationApiClient(ContentResolver resolver){this.resolver=resolver;}
    static String endpoint(String base,String date)throws Exception{return base.replaceAll("/+$","")+"/upload?analyze=true&full=true&date="+URLEncoder.encode(date,"UTF-8");}
    static String classify(int status){if(status==401)return "unauthorized";if(status>=500)return "server_error";return status>=200&&status<300?"ok":"http_error";}
    static boolean tooLarge(long size){return size>MAX;}
    static Job uploadJob(Result result){try{if(!"ok".equals(result.code))return new Job(result.code,"");JsonObject j=JsonParser.parseString(result.body).getAsJsonObject();String id=j.get("request_id").getAsString();return new Job(j.has("reused")&&j.get("reused").getAsBoolean()?"reused":"queued",id);}catch(Exception e){return new Job("protocol_error","");}}
    static Job statusJob(Result result,String expectedDate){try{if(!"ok".equals(result.code))return new Job(result.code,"");JsonObject j=JsonParser.parseString(result.body).getAsJsonObject();String state=j.get("status").getAsString(),date=j.has("date")&&!j.get("date").isJsonNull()?j.get("date").getAsString():"";if(!date.isEmpty()&&!expectedDate.equals(date))return new Job("date_mismatch","");if(!java.util.Arrays.asList("queued","running","done","reused","error").contains(state))return new Job("protocol_error","");JsonObject data=j.has("result")&&j.get("result").isJsonObject()?j.getAsJsonObject("result"):new JsonObject();boolean ready=data.has("report_status")&&data.get("report_status").getAsInt()>=2&&data.has("full_report_state")&&"generated".equals(data.get("full_report_state").getAsString())&&((data.has("analysis_report")&&!data.get("analysis_report").getAsString().trim().isEmpty())||(data.has("analysis_html")&&!data.get("analysis_html").getAsString().trim().isEmpty()));return new Job(state,j.get("request_id").getAsString(),ready);}catch(Exception e){return new Job("protocol_error","");}}
    static String statusEndpoint(String base,String id)throws Exception{return base.replaceAll("/+$","")+"/status/"+URLEncoder.encode(id,"UTF-8");}

    Result upload(String uri,String date,String base,String token){HttpURLConnection c=null;
        try(AssetFileDescriptor fd=resolver.openAssetFileDescriptor(Uri.parse(uri),"r")){if(fd!=null&&tooLarge(fd.getLength()))return new Result("too_large","");
            String boundary="MTLSleepBoundary";c=(HttpURLConnection)new URL(endpoint(base,date)).openConnection();c.setConnectTimeout(30000);c.setReadTimeout(30000);c.setDoOutput(true);c.setRequestMethod("POST");c.setRequestProperty("Authorization","Bearer "+token);c.setRequestProperty("Content-Type","multipart/form-data; boundary="+boundary);c.setChunkedStreamingMode(8192);
            try(OutputStream out=c.getOutputStream();InputStream in=resolver.openInputStream(Uri.parse(uri))){out.write(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sleep.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").getBytes("UTF-8"));byte[] buf=new byte[8192];long total=0;for(int n;(n=in.read(buf))>=0;){total+=n;if(tooLarge(total))return new Result("too_large","");out.write(buf,0,n);}out.write(("\r\n--"+boundary+"--\r\n").getBytes("UTF-8"));}
            int status=c.getResponseCode();return new Result(classify(status),read(status<400?c.getInputStream():c.getErrorStream()));
        }catch(SocketTimeoutException e){return new Result("timeout","");}catch(Exception e){return new Result("network_error","");}finally{if(c!=null)c.disconnect();}}
    Result status(String id,String date,String base,String token){HttpURLConnection c=null;try{c=(HttpURLConnection)new URL(statusEndpoint(base,id)).openConnection();c.setConnectTimeout(30000);c.setReadTimeout(30000);c.setRequestProperty("Authorization","Bearer "+token);int status=c.getResponseCode();return new Result(classify(status),read(status<400?c.getInputStream():c.getErrorStream()));}catch(SocketTimeoutException e){return new Result("timeout","");}catch(Exception e){return new Result("network_error","");}finally{if(c!=null)c.disconnect();}}
    private static String read(InputStream in)throws Exception{if(in==null)return "";try(InputStream source=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[2048];for(int n;(n=source.read(b))>=0;)out.write(b,0,n);return out.toString("UTF-8");}}
}
