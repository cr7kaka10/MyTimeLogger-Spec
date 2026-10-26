package com.mytimelogger.app;

import android.content.Context;
import java.util.Collections;
import java.util.List;
import java.util.Map;

final class MorningDiaryStore {
    static final String WRITTEN="written", MISSING="missing", UNKNOWN="unknown";
    static String classify(Object value){return value instanceof String&&!((String)value).trim().isEmpty()?WRITTEN:MISSING;}
    static String today(Context context,String date){
        String name=new WidgetTimerPreferences(context).loadActiveDatabaseName();
        if(name==null||!context.getDatabasePath(name).isFile())return UNKNOWN;
        SqliteConnection db=new SqliteConnection(context,name);
        try{db.open();List<Map<String,Object>> rows=db.query(
                "SELECT morning_diary FROM huawei_sleep_data WHERE date=? LIMIT 1",Collections.singletonList(date));
            return classify(rows.isEmpty()?null:rows.get(0).get("morning_diary"));
        }catch(RuntimeException error){return UNKNOWN;}finally{db.close();}
    }
    private MorningDiaryStore(){}
}
