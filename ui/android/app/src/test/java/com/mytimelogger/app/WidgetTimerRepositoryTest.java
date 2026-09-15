package com.mytimelogger.app;

import static org.junit.Assert.*;
import android.database.sqlite.SQLiteException;
import java.util.*;
import org.junit.Test;

public class WidgetTimerRepositoryTest {
    private static class Storage implements WidgetTimerRepository.StoragePort {
        String executeSql; List<?> values; boolean inTransaction; boolean rolledBack;
        public List<Map<String, Object>> query(String sql, List<?> parameters) { return Collections.emptyList(); }
        public void execute(String sql, List<?> parameters) {
            if (!inTransaction) throw new AssertionError("write outside transaction");
            executeSql = sql; values = parameters;
        }
        public void transaction(Runnable body) {
            inTransaction = true;
            try { body.run(); } catch (RuntimeException error) { executeSql = null; values = null; rolledBack = true; throw error; }
            finally { inTransaction = false; }
        }
    }
    @Test public void categoriesUseAuthoritativeDatabaseAndSavedOrderContract() {
        final String[] sql = {null};
        WidgetTimerRepository.QueryPort port = (statement, parameters) -> {
            sql[0] = statement;
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", 7L); row.put("name", "副业研发"); row.put("icon", "atm:st_024"); row.put("color", "#123456");
            return Collections.singletonList(row);
        };
        WidgetTimerRepository repository = new WidgetTimerRepository(port);
        List<WidgetTimerRepository.Category> categories = repository.loadCategories();
        assertEquals("my_time_logger.db", WidgetTimerRepository.DATABASE_NAME);
        assertTrue(sql[0].contains("WHERE is_active = 1"));
        assertTrue(sql[0].contains("ORDER BY sort_order"));
        assertTrue(sql[0].contains("LIMIT 15"));
        assertEquals(1, categories.size());
        assertEquals(7L, categories.get(0).id);
        assertEquals("副业研发", categories.get(0).name);
        assertEquals("atm:st_024", categories.get(0).icon);
        assertEquals("#123456", categories.get(0).color);
    }

    @Test public void sessionWriteIsTransactionalSecondPreciseAndUnsynced() {
        Storage storage = new Storage();
        WidgetTimerRepository repository = new WidgetTimerRepository(storage);
        repository.saveSession(new WidgetTimerEngine.Session(7L, 1000L, 4500L, 3L));
        assertTrue(storage.executeSql.contains("INSERT INTO study_sessions"));
        assertTrue(storage.executeSql.contains("(id,start_time"));
        assertTrue(storage.executeSql.contains("pushed_at"));
        UUID.fromString(String.valueOf(storage.values.get(0)));
        assertEquals(3L, storage.values.get(4));
        assertEquals("1970-01-01", storage.values.get(5));
        assertEquals("星期四", storage.values.get(6));
        assertNull(storage.values.get(storage.values.size() - 1));
    }

    @Test public void sessionFailureRollsBackWithoutHalfRow() {
        Storage storage = new Storage() {
            public void execute(String sql, List<?> parameters) { throw new IllegalStateException("fixture"); }
        };
        assertThrows(IllegalStateException.class, () -> new WidgetTimerRepository(storage)
                .saveSession(new WidgetTimerEngine.Session(7L, 1000L, 4500L, 3L)));
        assertTrue(storage.rolledBack); assertNull(storage.values);
    }

    @Test public void missingCategoryTableReturnsSafeEmptyStateWithoutCreatingSchema() {
        WidgetTimerRepository.QueryPort uninitialized = (sql, parameters) -> {
            throw new SQLiteException() {
                @Override public String getMessage() { return "no such table: categories"; }
            };
        };
        assertTrue(new WidgetTimerRepository(uninitialized).loadCategories().isEmpty());
        assertFalse(WidgetTimerRepository.categorySqlForTest().toUpperCase(Locale.ROOT).contains("CREATE TABLE"));
    }

    @Test public void olderRevisionCannotReplaceAuthoritativeSnapshot() {
        assertFalse(WidgetTimerRepository.acceptsRevision(12L, 11L));
        assertTrue(WidgetTimerRepository.acceptsRevision(12L, 12L));
        assertTrue(WidgetTimerRepository.acceptsRevision(12L, 13L));
    }
}
