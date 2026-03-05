import pytest

from insightxpert.db.connector import DatabaseConnector


class TestDialectProperty:
    """Tests for the DatabaseConnector.dialect property."""

    def test_dialect_before_connect_raises(self):
        """Accessing dialect before connect() raises RuntimeError."""
        db = DatabaseConnector()
        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = db.dialect


class TestReadOnlyMode:
    """Tests for the read_only parameter on execute()."""

    def test_read_only_mode_select(self, db_connector):
        """execute() with read_only=True does not raise for SELECT."""
        rows = db_connector.execute("SELECT * FROM users", read_only=True)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"


class TestConnectionPoolSettings:
    """Tests for pool configuration set during connect()."""

    def test_connect_sets_pool_pre_ping(self, db_connector):
        """Engine has pool_pre_ping enabled after connect."""
        assert db_connector.engine.pool._pre_ping is True
