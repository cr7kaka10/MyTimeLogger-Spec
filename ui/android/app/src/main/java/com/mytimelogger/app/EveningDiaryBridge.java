package com.mytimelogger.app;

import android.content.Context;
import android.webkit.JavascriptInterface;

public final class EveningDiaryBridge {
    static final String JAVASCRIPT_NAME="MTLEveningDiary";
    private final Context context;
    EveningDiaryBridge(Context context){this.context=context.getApplicationContext();}
    @JavascriptInterface public void refresh(){EveningDiaryReminderReceiver.reconcile(context);}
    @JavascriptInterface public void saved(String date){long now=System.currentTimeMillis();if(MorningDiaryReminderReceiver.today(now).equals(date)){EveningDiaryReminderReceiver.cancel(context);EveningDiaryReminderReceiver.scheduleAt(context,EveningDiaryReminderReceiver.tomorrowStart(now));}else refresh();}
}
