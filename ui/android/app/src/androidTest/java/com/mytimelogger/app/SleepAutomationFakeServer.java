package com.mytimelogger.app;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

final class SleepAutomationFakeServer implements AutoCloseable {
    private final ServerSocket socket;
    private final Thread worker;
    final List<String> requests=Collections.synchronizedList(new ArrayList<>());
    private final String date;
    SleepAutomationFakeServer(String date) throws Exception {
        this.date=date;socket=new ServerSocket(0,5,InetAddress.getByName("127.0.0.1"));socket.setSoTimeout(15000);
        worker=new Thread(this::serve,"sleep-fake-server");worker.start();
    }
    String url(){return "http://127.0.0.1:"+socket.getLocalPort();}
    private static String line(InputStream in) throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();int b;
        while((b=in.read())!=-1&&b!='\n')if(b!='\r')out.write(b);
        return out.toString("UTF-8");
    }
    private static void skip(InputStream in,long count) throws IOException {
        byte[] buffer=new byte[4096];while(count>0){int read=in.read(buffer,0,(int)Math.min(buffer.length,count));if(read<0)throw new EOFException();count-=read;}
    }
    private void serve(){
        try {for(int i=0;i<5;i++)try(Socket client=socket.accept()){
            InputStream in=client.getInputStream();String path=line(in).split(" ")[1],header;int length=0;boolean chunked=false;
            while(!(header=line(in)).isEmpty()){
                String value=header.toLowerCase(Locale.ROOT);
                if(value.startsWith("content-length:"))length=Integer.parseInt(header.substring(15).trim());
                if(value.startsWith("transfer-encoding:")&&value.contains("chunked"))chunked=true;
            }
            if(chunked){while(true){int size=Integer.parseInt(line(in).split(";",2)[0],16);if(size==0){line(in);break;}skip(in,size);line(in);}}
            else skip(in,length);
            requests.add(path);
            String body=path.startsWith("/status_by_date/")?"{\"detail\":\"date not found\"}":path.startsWith("/upload?")?"{\"request_id\":\"ocr\"}":path.equals("/status/ocr")?"{\"request_id\":\"ocr\",\"status\":\"uploaded\",\"date\":\""+date+"\"}":path.equals("/generate_report")?"{\"request_id\":\"report\"}":"{\"request_id\":\"report\",\"status\":\"done\",\"date\":\""+date+"\",\"result\":{\"report_status\":1,\"analysis_report\":\"test report\"}}";
            byte[] data=body.getBytes(StandardCharsets.UTF_8);String code=path.startsWith("/status_by_date/")?"404 Not Found":"200 OK";
            OutputStream out=client.getOutputStream();out.write(("HTTP/1.1 "+code+"\r\nContent-Type: application/json\r\nContent-Length: "+data.length+"\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.UTF_8));out.write(data);out.flush();
        }}catch(Exception ignored){}
    }
    public void close() throws Exception {socket.close();worker.join(1000);}
}
