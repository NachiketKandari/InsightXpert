import pytest
from sqlalchemy import create_engine

from insightxpert.db.connector import DatabaseConnector
from insightxpert.db.schema import get_schema_ddl, get_table_info


def test_connect_and_get_tables(test_db):
    db = DatabaseConnector()
    db.connect(test_db)
    tables = db.get_tables()
    assert "users" in tables
    assert "orders" in tables
    db.disconnect()


def test_execute_select(test_db):
    db = DatabaseConnector()
    db.connect(test_db)
    rows = db.execute("SELECT * FROM users ORDER BY id")
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"
    assert rows[1]["name"] == "Bob"
    db.disconnect()


def test_execute_aggregate(test_db):
    db = DatabaseConnector()
    db.connect(test_db)
    rows = db.execute("SELECT COUNT(*) as cnt FROM orders")
    assert rows[0]["cnt"] == 3
    db.disconnect()


def test_execute_row_limit(test_db):
    db = DatabaseConnector()
    db.connect(test_db)
    rows = db.execute("SELECT * FROM orders", row_limit=2)
    assert len(rows) == 2
    db.disconnect()


def test_get_schema_ddl(test_db):
    engine = create_engine(test_db)
    ddl = get_schema_ddl(engine)
    assert "CREATE TABLE users" in ddl
    assert "CREATE TABLE orders" in ddl
    assert "FOREIGN KEY" in ddl
    engine.dispose()


def test_get_table_info(test_db):
    engine = create_engine(test_db)
    info = get_table_info(engine, "users")
    assert info["table_name"] == "users"
    col_names = [c["name"] for c in info["columns"]]
    assert "id" in col_names
    assert "name" in col_names
    assert "email" in col_names
    engine.dispose()


def test_disconnect_without_connect():
    db = DatabaseConnector()
    db.disconnect()  # Should not raise


def test_execute_without_connect():
    db = DatabaseConnector()
    with pytest.raises(RuntimeError, match="not connected"):
        db.execute("SELECT 1")
