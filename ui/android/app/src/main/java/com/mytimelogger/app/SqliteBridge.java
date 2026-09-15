package com.mytimelogger.app;
import android.content.Context;
import android.webkit.JavascriptInterface;
import java.util.*;
import org.json.*;
public final class SqliteBridge {
    static final String JAVASCRIPT_NAME = "MyTimeLoggerSqlite";
    private static final String OK = "{\"ok\":true}";
    private final Context context; private SqliteConnection connection;
    SqliteBridge(Context context) { this.context = context.getApplicationContext(); }
    @JavascriptInterface public synchronized String open(String name) {
        try {
            SqliteConnection next = new SqliteConnection(context, name);
            next.open();
            if (connection != null) connection.close();
            connection = next; return OK;
        } catch (IllegalArgumentException error) { return failure("invalid_bridge_arguments"); }
        catch (RuntimeException error) { return operationFailure("open", null, error, "sqlite_open_failed"); }
    }
    @JavascriptInterface public synchronized String close() { try { if (connection != null) connection.close(); connection = null; return OK; }
        catch (RuntimeException error) { return operationFailure("close", null, error, "sqlite_close_failed"); } }
    @JavascriptInterface public synchronized String execute(String sql, String parametersJson) {
        if (connection == null) return failure("sqlite_not_initialized");
        try { connection.execute(sql, parameters(parametersJson)); return OK; }
        catch (JSONException | IllegalArgumentException error) { return failure("invalid_bridge_arguments"); }
        catch (RuntimeException error) { return operationFailure("execute", null, error, "sqlite_operation_failed"); }
    }
    @JavascriptInterface public synchronized String query(String sql, String parametersJson) {
        if (connection == null) return failure("sqlite_not_initialized");
        try { return "{\"ok\":true,\"rows\":" + new JSONArray(connection.query(sql, parameters(parametersJson))) + "}"; }
        catch (JSONException | IllegalArgumentException error) { return failure("invalid_bridge_arguments"); }
        catch (RuntimeException error) { return operationFailure("query", null, error, "sqlite_operation_failed"); }
    }
    @JavascriptInterface public synchronized String transaction(String operationsJson) {
        if (connection == null) return failure("sqlite_not_initialized");
        try {
            JSONArray source = new JSONArray(operationsJson == null ? "[]" : operationsJson);
            List<String> statements = new ArrayList<>(); List<List<Object>> values = new ArrayList<>();
            for (int index = 0; index < source.length(); index++) {
                JSONObject operation = source.getJSONObject(index);
                statements.add(operation.getString("sql"));
                values.add(parameters(operation.optJSONArray("params") == null ? "[]" : operation.getJSONArray("params").toString()));
            }
            connection.executeBatch(statements, values); return OK;
        } catch (JSONException | IllegalArgumentException error) { return failure("invalid_bridge_arguments"); }
        catch (SqliteConnection.BatchException error) { return operationFailure("transaction", error.index, error, "sqlite_operation_failed"); }
        catch (RuntimeException error) { return operationFailure("transaction", null, error, "sqlite_operation_failed"); }
    }
    private static List<Object> parameters(String json) throws JSONException {
        JSONArray source = new JSONArray(json == null || json.trim().isEmpty() ? "[]" : json);
        List<Object> values = new ArrayList<>();
        for (int i = 0; i < source.length(); i++) {
            Object value = source.get(i);
            if (value == JSONObject.NULL) value = null;
            else if (value instanceof JSONObject) {
                JSONObject object = (JSONObject) value;
                if (object.length() != 1 || !object.has("$blob")) throw new JSONException("invalid_blob");
                value = Collections.<String, Object>singletonMap("$blob", object.getString("$blob"));
            }
            values.add(value);
        }
        return values;
    }
    private static String failure(String code) { return "{\"ok\":false,\"error\":\"" + code + "\"}"; }
    static String operationFailure(String operation, Integer index, Throwable error, String code) {
        return "{\"ok\":false,\"error\":\"" + code + "\",\"operation\":\"" + operation
                + "\"" + (index == null ? "" : ",\"index\":" + index)
                + ",\"error_category\":\"" + SqliteConnection.errorCategory(error) + "\"}";
    }
}
