package com.mytimelogger.app;

import android.content.Intent;
import android.widget.RemoteViewsService;

public final class TimerWidgetViewsService extends RemoteViewsService {
    @Override public RemoteViewsFactory onGetViewFactory(Intent intent) {
        return new TimerWidgetViewsFactory(this, new WidgetTimerRepository(this));
    }
}
