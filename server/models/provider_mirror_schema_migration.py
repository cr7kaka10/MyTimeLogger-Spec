import sqlite3


PROVIDER_TABLES = ("server_tasks", "server_habits", "server_habit_checkins")


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _column_definition(row: tuple) -> str:
    _, name, column_type, not_null, default_value, _ = row
    parts = [_quoted(name), column_type or "TEXT"]
    if not_null or name in {"id", "user_id"}:
        parts.append("NOT NULL")
    if default_value is not None:
        parts.extend(("DEFAULT", str(default_value)))
    return " ".join(parts)


def _has_user_scoped_primary_key(conn: sqlite3.Connection, table: str) -> bool:
    primary_key = {
        row[1]: row[5]
        for row in conn.execute(f"PRAGMA table_info({_quoted(table)})").fetchall()
        if row[5]
    }
    return primary_key == {"user_id": 1, "id": 2}


def _table_constraints(table: str) -> list[str]:
    constraints = ["PRIMARY KEY (user_id, id)", "FOREIGN KEY (user_id) REFERENCES users(id)"]
    if table == "server_tasks":
        constraints.append("FOREIGN KEY (category_id) REFERENCES server_categories(id)")
    elif table == "server_habit_checkins":
        constraints.extend((
            "FOREIGN KEY (user_id, habit_id) REFERENCES server_habits(user_id, id)",
            "UNIQUE (user_id, habit_id, checkin_date)",
        ))
    return constraints


def _group_counts(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return conn.execute(
        f"SELECT user_id, COUNT(*) FROM {_quoted(table)} GROUP BY user_id ORDER BY user_id"
    ).fetchall()


def _rebuild_table(conn: sqlite3.Connection, table: str) -> None:
    columns = conn.execute(f"PRAGMA table_info({_quoted(table)})").fetchall()
    if not columns:
        raise RuntimeError(f"provider_mirror_table_missing:{table}")
    column_names = [row[1] for row in columns]
    before_total = conn.execute(f"SELECT COUNT(*) FROM {_quoted(table)}").fetchone()[0]
    before_groups = _group_counts(conn, table)
    auxiliary_sql = [
        row[0] for row in conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",
            (table,),
        ).fetchall()
    ]
    replacement = f"_provider_scoped_{table}"
    conn.execute(f"DROP TABLE IF EXISTS {_quoted(replacement)}")
    definitions = [_column_definition(row) for row in columns] + _table_constraints(table)
    conn.execute(f"CREATE TABLE {_quoted(replacement)} ({', '.join(definitions)})")
    column_sql = ", ".join(_quoted(name) for name in column_names)
    conn.execute(
        f"INSERT INTO {_quoted(replacement)} ({column_sql}) SELECT {column_sql} FROM {_quoted(table)}"
    )
    copied_total = conn.execute(f"SELECT COUNT(*) FROM {_quoted(replacement)}").fetchone()[0]
    copied_groups = _group_counts(conn, replacement)
    if copied_total != before_total or copied_groups != before_groups:
        raise RuntimeError(f"provider_mirror_copy_mismatch:{table}")
    conn.execute(f"DROP TABLE {_quoted(table)}")
    conn.execute(f"ALTER TABLE {_quoted(replacement)} RENAME TO {_quoted(table)}")
    for statement in auxiliary_sql:
        conn.execute(statement)


def migrate_provider_mirror_identity(conn: sqlite3.Connection) -> bool:
    """Rebuild provider mirrors around (user_id, id), atomically and idempotently."""
    pending = [table for table in PROVIDER_TABLES if not _has_user_scoped_primary_key(conn, table)]
    if not pending:
        return False
    conn.commit()
    foreign_keys = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table in PROVIDER_TABLES:
            if table in pending:
                _rebuild_table(conn, table)
        violations = [
            row for row in conn.execute("PRAGMA foreign_key_check").fetchall()
            if row[0] in PROVIDER_TABLES
        ]
        if violations:
            raise RuntimeError(f"provider_mirror_foreign_key_check_failed:{len(violations)}")
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}")
