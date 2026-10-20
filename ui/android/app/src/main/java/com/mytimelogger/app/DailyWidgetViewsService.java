package com.mytimelogger.app;

import android.content.Intent;
import android.widget.RemoteViewsService;

public final class DailyWidgetViewsService extends RemoteViewsService {
    @Override public RemoteViewsFactory onGetViewFactory(Intent intent) {
        return new DailyWidgetViewsFactory(this);
    }
}
