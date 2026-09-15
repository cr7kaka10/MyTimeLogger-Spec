package com.mytimelogger.app;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public final class WidgetTimerApiClient {
    static final long DEFAULT_DEADLINE_MS=8_000L;
    interface Clock { long now(); }
    interface Transport { Response request(String method,String url,Map<String,String> headers,String body,int timeoutMs) throws Exception; }
    static final class Response { final int code; final String body; Response(int code,String body){this.code=code;this.body=body;} }
    public static final class Outcome { public final String status; public final WidgetTimerCurrentState state; Outcome(String status,WidgetTimerCurrentState state){this.status=status;this.state=state;} public boolean applied(){return "applied".equals(status);} }
    private final Transport transport; private final Clock clock; private final long deadlineMs;
    public WidgetTimerApiClient(){this(new HttpTransport(),System::currentTimeMillis,DEFAULT_DEADLINE_MS);}
    WidgetTimerApiClient(Transport transport,Clock clock,long deadlineMs){this.transport=transport;this.clock=clock;this.deadlineMs=deadlineMs;}

    public Outcome readCurrentState(WidgetTimerRuntimeStore.Config runtime) {
        if(runtime==null||runtime.serverUrl==null||runtime.serverUrl.isEmpty()
                ||runtime.authToken==null||runtime.authToken.isEmpty())return new Outcome("unavailable",null);
        long deadline=clock.now()+deadlineMs; try {
            Response read=request("GET",runtime.serverUrl+"/api/timer/current",runtime,null,deadline);
            if(clock.now()>deadline)return new Outcome("timeout",null);
            if(read.code==401||read.code==403)return new Outcome("unauthorized",null);
            WidgetTimerCurrentState current=read.code/100==2?WidgetTimerCurrentState.parse(read.body):null;
            return current==null?new Outcome("failed",null):new Outcome("applied",current);
        } catch(java.net.SocketTimeoutException timeout){return new Outcome("timeout",null);}
        catch(Exception ignored){return new Outcome("network",null);}
    }

    public Outcome execute(WidgetTimerRuntimeStore.Config runtime,WidgetTimerCommand command,String targetName) {
        if(runtime==null||command==null||targetName==null||WidgetTimerCommand.isBlockedCategoryName(targetName))return new Outcome("unavailable",null);
        long deadline=clock.now()+deadlineMs; try {
            Response read=request("GET",runtime.serverUrl+"/api/timer/current",runtime,null,deadline);
            if(read.code==401||read.code==403)return new Outcome("unauthorized",null);
            WidgetTimerCurrentState current=read.code/100==2?WidgetTimerCurrentState.parse(read.body):null; if(current==null)return new Outcome("failed",null);
            for(int attempt=0;attempt<2;attempt++){
                String operation=operation(command,current); if(operation==null)return new Outcome("applied",current);
                String body=payload(runtime,command,targetName,current.revision,operation,attempt + 1);
                Response sent=request("POST",runtime.serverUrl+"/api/timer/current/"+operation,runtime,body,deadline);
                if(clock.now()>deadline)return new Outcome("timeout",null);
                if(sent.code==401||sent.code==403)return new Outcome("unauthorized",null);
                WidgetTimerCurrentState next=WidgetTimerCurrentState.parse(sent.body);
                JsonObject envelope=parse(sent.body); String status=envelope==null?null:string(envelope,"status");
                if(sent.code/100==2&&"accepted".equals(status)&&next!=null)return new Outcome("applied",next);
                if(attempt==0&&"conflict".equals(status)&&"stale_timer_revision".equals(string(envelope,"error_code"))&&next!=null){current=next;continue;}
                return new Outcome("failed",null);
            }
        } catch(java.net.SocketTimeoutException timeout){return new Outcome("timeout",null);} catch(Exception ignored){return new Outcome("network",null);}
        return new Outcome("failed",null);
    }
    private Response request(String method,String url,WidgetTimerRuntimeStore.Config runtime,String body,long deadline)throws Exception{
        long remaining=deadline-clock.now(); if(remaining<=0)throw new java.net.SocketTimeoutException();
        Map<String,String> headers=new LinkedHashMap<>(); headers.put("Authorization","Bearer "+runtime.authToken); headers.put("X-MTL-Timer-State","timer-current-state-v1");
        if(body!=null)headers.put("Content-Type","application/json"); return transport.request(method,url,headers,body,(int)Math.max(1,Math.min(Integer.MAX_VALUE,remaining/2)));
    }
    static String operation(WidgetTimerCommand command,WidgetTimerCurrentState current){
        if("stop".equals(command.action))return current.active?"stop":null;
        if(current.active&&current.categoryId==command.categoryId)return null; return current.active?"switch":"start";
    }
    private static String payload(WidgetTimerRuntimeStore.Config runtime,WidgetTimerCommand command,String name,long revision,String operation,int attempt){
        JsonObject body=new JsonObject(); body.addProperty("session_id","widget-"+command.commandId); body.addProperty("device_id",runtime.deviceId);
        body.addProperty("observed_revision",revision); body.addProperty("idempotency_key",command.commandId+":"+attempt); body.addProperty("user_intent_id",command.commandId);
        body.addProperty("category_id",command.categoryId); body.addProperty("category_name",name); body.addProperty("current_note",""); body.addProperty("timer_mode","countup"); body.addProperty("duration_ms",0);
        if("stop".equals(operation))body.addProperty("session_summary",""); return body.toString();
    }
    private static JsonObject parse(String raw){try{return JsonParser.parseString(raw).getAsJsonObject();}catch(Exception ignored){return null;}}
    private static String string(JsonObject value,String key){try{return value.get(key).getAsString();}catch(Exception ignored){return null;}}
    private static final class HttpTransport implements Transport {
        public Response request(String method,String url,Map<String,String> headers,String body,int timeoutMs)throws Exception{
            HttpURLConnection connection=(HttpURLConnection)new URL(url).openConnection(); try{
                connection.setRequestMethod(method); connection.setConnectTimeout(timeoutMs); connection.setReadTimeout(timeoutMs); for(Map.Entry<String,String> item:headers.entrySet())connection.setRequestProperty(item.getKey(),item.getValue());
                if(body!=null){connection.setDoOutput(true);try(OutputStream output=connection.getOutputStream()){output.write(body.getBytes(StandardCharsets.UTF_8));}}
                int code=connection.getResponseCode(); InputStream input=code>=400?connection.getErrorStream():connection.getInputStream(); if(input==null)return new Response(code,"");
                try(InputStream stream=input;ByteArrayOutputStream output=new ByteArrayOutputStream()){byte[] buffer=new byte[4096];int read;while((read=stream.read(buffer))>=0)output.write(buffer,0,read);return new Response(code,output.toString("UTF-8"));}
            }finally{connection.disconnect();}
        }
    }
}
