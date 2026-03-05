import pytest
from sqlalchemy import text, create_engine

from insightxpert.db.connector import DatabaseConnector


class TestDialectProperty:
    """Tests for the DatabaseConnector.dialect property."""

    def test_dialect_property(self, sqlite_db):
        """After connecting to SQLite, dialect returns 'sqlite'."""
        db = DatabaseConnector()
        db.connect(sqlite_db)
        try:
            assert db.dialect == "sqlite"
        finally:
            db.disconnect()

    def test_dialect_before_connect_raises(self):
        """Accessing dialect before connect() raises RuntimeError."""
        db = DatabaseConnector()
        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = db.dialect


class TestReadOnlyMode:
    """Tests for the read_only parameter on execute()."""

    def test_read_only_mode_sqlite(self, db_connector):
        """execute() with read_only=True does not raise for SELECT on SQLite."""
        rows = db_connector.execute("SELECT * FROM users", read_only=True)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"

    def test_read_only_mode_blocks_writes(self, db_connector):
        """execute() with read_only=True blocks INSERT on SQLite via PRAGMA query_only."""
        with pytest.raises(Exception):
            db_connector.execute(
                "INSERT INTO users (id, name, email) VALUES (99, 'Eve', 'eve@example.com')",
                read_only=True,
            )


class TestSQLiteForeignKeys:
    """Tests for the SQLite foreign key enforcement listener."""

    def test_sqlite_foreign_keys_enabled(self, db_connector):
        """PRAGMA foreign_keys is ON after connect for SQLite."""
        rows = db_connector.execute("PRAGMA foreign_keys")
        assert rows[0]["foreign_keys"] == 1

    def test_foreign_key_constraint_enforced(self, db_connector):
        """Inserting a row with a non-existent FK reference is rejected."""
        with pytest.raises(Exception):
            db_connector.execute(
                "INSERT INTO orders (id, user_id, amount) VALUES (100, 9999, 10.0)"
            )


class TestConnectionPoolSettings:
    """Tests for pool configuration set during connect()."""

    def test_connect_sets_pool_pre_ping(self, db_connector):
        """Engine has pool_pre_ping enabled after connect."""
        assert db_connector.engine.pool._pre_ping is True
