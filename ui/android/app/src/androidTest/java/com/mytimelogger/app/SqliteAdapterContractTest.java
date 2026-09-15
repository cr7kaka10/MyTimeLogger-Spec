package com.mytimelogger.app;
import static org.junit.Assert.assertEquals;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.*;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
@RunWith(AndroidJUnit4.class)
public class SqliteAdapterContractTest {
    @Test public void androidAdapterMatchesSharedContract() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        JSONArray scenarios = contract(InstrumentationRegistry.getInstrumentation().getContext());
        for (int index = 0; index < scenarios.length(); index++) {
            JSONObject scenario = scenarios.getJSONObject(index);
            String name = "sqlite-contract-" + index + ".db";
            context.deleteDatabase(name);
            SqliteConnection connection = new SqliteConnection(context, name);
            try {
                connection.open();
                JSONArray steps = scenario.getJSONArray("steps");
                for (int stepIndex = 0; stepIndex < steps.length(); stepIndex++) {
                    JSONObject step = steps.getJSONObject(stepIndex);
                    if (step.has("exec")) connection.execute(step.getString("exec"), Collections.emptyList());
                    else if (step.has("run")) connection.execute(step.getString("run"), parameters(step.optJSONArray("params")));
                    else assertEquals(scenario.getString("name"), step.getJSONArray("expect").toString(),
                        new JSONArray(connection.query(step.getString("query"), parameters(step.optJSONArray("params")))).toString());
                }
            } finally { connection.close(); context.deleteDatabase(name); }
        }
    }
    private static JSONArray contract(Context context) throws Exception {
        try (Scanner scanner = new Scanner(context.getAssets().open("sqlite-adapter-contract.json"), "UTF-8").useDelimiter("\\A")) {
            return new JSONArray(scanner.next());
        }
    }
    private static List<Object> parameters(JSONArray source) throws JSONException {
        if (source == null) return Collections.emptyList();
        List<Object> values = new ArrayList<>();
        for (int index = 0; index < source.length(); index++) {
            Object value = source.get(index); values.add(value == JSONObject.NULL ? null : value);
        }
        return values;
    }
}
