package com.mytimelogger.app;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteCursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteProgram;
import android.database.sqlite.SQLiteQuery;
import android.database.sqlite.SQLiteStatement;
import java.io.File;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
final class SqliteConnection {
    interface TransactionBody { void run(); }
    static final class BatchException extends RuntimeException {
        final int index;
        BatchException(int index, RuntimeException cause) { super(cause); this.index = index; }
    }
    static String errorCategory(Throwable error) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            String text = (current.getClass().getSimpleName() + " " + current.getMessage()).toLowerCase();
            if (text.contains("constraint")) return "constraint";
            if (text.contains("locked") || text.contains("busy")) return "locked";
            if (text.contains("column") || text.contains("table") || text.contains("schema")) return "schema";
            if (text.contains("disk") || text.contains("storage") || text.contains("readonly") || text.contains("i/o")) return "storage";
        }
        return "unknown";
    }
    private final File databaseFile;
    private SQLiteDatabase database;
    SqliteConnection(Context context, String name) {
        if (name == null || name.trim().isEmpty() || name.contains("/") || name.contains("\\")) throw new IllegalArgumentException("invalid_database_name");
        databaseFile = context.getApplicationContext().getDatabasePath(name);
    }
    synchronized void open() {
        if (database != null && database.isOpen()) return;
        File parent = databaseFile.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IllegalStateException("database_directory_unavailable");
        }
        database = SQLiteDatabase.openOrCreateDatabase(databaseFile, null);
    }
    synchronized void close() {
        if (database != null) database.close();
        database = null;
    }
    synchronized void execute(String sql, List<?> parameters) {
        SQLiteStatement statement = requireDatabase().compileStatement(sql);
        try { bind(statement, parameters); statement.execute(); }
        finally { statement.close(); }
    }
    synchronized List<Map<String, Object>> query(String sql, List<?> parameters) {
        Cursor cursor = requireDatabase().rawQueryWithFactory((db, driver, table, query) -> {
            bind(query, parameters); return new SQLiteCursor(driver, table, query);
        }, sql, null, null);
        try {
            List<Map<String, Object>> rows = new ArrayList<>();
            String[] columns = cursor.getColumnNames();
            while (cursor.moveToNext()) {
                Map<String, Object> row = new LinkedHashMap<>();
                for (int index = 0; index < columns.length; index++) row.put(columns[index], read(cursor, index));
                rows.add(row);
            }
            return rows;
        } finally { cursor.close(); }
    }
    synchronized void transaction(TransactionBody body) {
        SQLiteDatabase target = requireDatabase();
        if (target.inTransaction()) throw new IllegalStateException("nested_transaction_not_supported");
        target.beginTransaction();
        try {
            body.run();
            target.setTransactionSuccessful();
        } finally {
            target.endTransaction();
        }
    }
    synchronized void executeBatch(List<String> statements, List<List<Object>> parameters) {
        if (statements.size() != parameters.size()) throw new IllegalArgumentException("invalid_batch");
        transaction(() -> {
            for (int index = 0; index < statements.size(); index++) {
                try { execute(statements.get(index), parameters.get(index)); }
                catch (RuntimeException error) { throw new BatchException(index, error); }
            }
        });
    }
    private static Object read(Cursor cursor, int index) {
        switch (cursor.getType(index)) {
            case Cursor.FIELD_TYPE_NULL: return null;
            case Cursor.FIELD_TYPE_INTEGER: return cursor.getLong(index);
            case Cursor.FIELD_TYPE_FLOAT: return cursor.getDouble(index);
            case Cursor.FIELD_TYPE_BLOB: return SqliteValueCodec.encode(cursor.getBlob(index));
            default: return cursor.getString(index);
        }
    }
    private SQLiteDatabase requireDatabase() {
        if (database == null || !database.isOpen()) throw new IllegalStateException("sqlite_not_open");
        return database;
    }
    private static void bind(SQLiteProgram statement, List<?> parameters) {
        if (parameters == null) return;
        for (int index = 0; index < parameters.size(); index++) {
            Object raw = parameters.get(index);
            Object value = raw instanceof Map<?, ?> ? SqliteValueCodec.decode(raw) : raw;
            int slot = index + 1;
            if (value == null) statement.bindNull(slot);
            else if (value instanceof byte[]) statement.bindBlob(slot, (byte[]) value);
            else if (value instanceof Float || value instanceof Double) statement.bindDouble(slot, ((Number) value).doubleValue());
            else if (value instanceof Number) statement.bindLong(slot, ((Number) value).longValue());
            else if (value instanceof String) statement.bindString(slot, (String) value);
            else throw new IllegalArgumentException("unsupported_sqlite_value");
        }
    }
}
