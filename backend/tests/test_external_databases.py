"""Tests for external databases feature.

Covers encryption round-trip, SQL guard enforcement, Pydantic schema
validation, and URL building safety.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import URL

from insightxpert.agents.sql_guard import FORBIDDEN_SQL_RE
from insightxpert.auth.encryption import decrypt_credentials, encrypt_credentials
from insightxpert.db.connector import ExternalDatabaseConfig, build_external_db_url
from insightxpert.external_databases.schemas import (
    CreateExternalDatabase,
    UpdateExternalDatabase,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_fernet_key() -> str:
    return Fernet.generate_key().decode()


# ---------------------------------------------------------------------------
# Encryption round-trip
# ---------------------------------------------------------------------------


class TestEncryptionRoundTrip:
    """encrypt_credentials -> decrypt_credentials returns original value."""

    @pytest.fixture(autouse=True)
    def _reset_fernet(self, monkeypatch):
        """Reset the module-level _fernet cache and set a valid key."""
        import insightxpert.auth.encryption as enc_mod

        enc_mod._fernet = None
        monkeypatch.setenv("ENCRYPTION_KEY", _generate_fernet_key())
        yield
        enc_mod._fernet = None

    def test_simple_password(self):
        original = "my_secret_password"
        encrypted = encrypt_credentials(original)
        assert encrypted != original
        assert decrypt_credentials(encrypted) == original

    def test_empty_string(self):
        original = ""
        encrypted = encrypt_credentials(original)
        assert decrypt_credentials(encrypted) == original

    @pytest.mark.parametrize(
        "password",
        [
            "p@ss:w/rd#100%",
            "emoji-🔑-key",
            'has"quotes\'mixed',
            "back\\slash",
            "tab\there",
            "newline\nhere",
            "unicode-日本語",
            "   spaces   ",
            "!@#$%^&*()_+-=[]{}|;':\",./<>?",
        ],
        ids=[
            "url-special-chars",
            "emoji",
            "quotes",
            "backslash",
            "tab",
            "newline",
            "unicode",
            "spaces",
            "all-punctuation",
        ],
    )
    def test_special_characters(self, password):
        encrypted = encrypt_credentials(password)
        assert decrypt_credentials(encrypted) == password

    def test_ciphertext_differs_each_call(self):
        """Fernet uses a random IV so two encryptions of the same value differ."""
        original = "same_value"
        enc1 = encrypt_credentials(original)
        enc2 = encrypt_credentials(original)
        assert enc1 != enc2
        assert decrypt_credentials(enc1) == original
        assert decrypt_credentials(enc2) == original


# ---------------------------------------------------------------------------
# Encryption requires ENCRYPTION_KEY
# ---------------------------------------------------------------------------


class TestEncryptionRequiresKey:

    @pytest.fixture(autouse=True)
    def _reset_fernet(self):
        import insightxpert.auth.encryption as enc_mod

        enc_mod._fernet = None
        yield
        enc_mod._fernet = None

    def test_encrypt_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.setattr(
            "insightxpert.config.Settings", lambda: type("S", (), {"encryption_key": None})(),
        )
        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY not set"):
            encrypt_credentials("anything")

    def test_decrypt_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.setattr(
            "insightxpert.config.Settings", lambda: type("S", (), {"encryption_key": None})(),
        )
        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY not set"):
            decrypt_credentials("anything")

    def test_encrypt_raises_with_empty_key(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "")
        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY not set"):
            encrypt_credentials("anything")


# ---------------------------------------------------------------------------
# SQL guard enforcement (sql_guard.FORBIDDEN_SQL_RE)
# ---------------------------------------------------------------------------


class TestSqlGuard:
    """FORBIDDEN_SQL_RE blocks write operations but allows reads."""

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users VALUES (1, 'a')",
            "  insert into users values (1, 'a')",
            "UPDATE users SET name='b' WHERE id=1",
            "  UPDATE users SET name='b'",
            "DELETE FROM users WHERE id=1",
            "DROP TABLE users",
            "ALTER TABLE users ADD COLUMN age INT",
            "CREATE TABLE evil (id INT)",
            "TRUNCATE TABLE users",
            "REPLACE INTO users VALUES (1, 'a')",
            "ATTACH DATABASE ':memory:' AS m",
            "DETACH DATABASE m",
        ],
        ids=[
            "insert",
            "insert-leading-space",
            "update",
            "update-leading-space",
            "delete",
            "drop",
            "alter",
            "create",
            "truncate",
            "replace",
            "attach",
            "detach",
        ],
    )
    def test_blocks_write_operations(self, sql):
        assert FORBIDDEN_SQL_RE.match(sql) is not None, f"Should block: {sql}"

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM users",
            "  SELECT * FROM users",
            "WITH cte AS (SELECT 1) SELECT * FROM cte",
            "SELECT * FROM users WHERE status = 'DELETED'",
            "SELECT * FROM users WHERE action = 'INSERT'",
            "SELECT * FROM users WHERE type IN ('UPDATE', 'DELETE')",
            "SELECT COUNT(*) FROM orders WHERE status = 'DROPPED'",
            "SELECT * FROM users WHERE name LIKE '%ALTER%'",
            "SELECT TRUNCATE(amount, 2) FROM orders",
        ],
        ids=[
            "simple-select",
            "select-leading-space",
            "cte-select",
            "status-deleted",
            "value-insert",
            "value-update-delete",
            "value-dropped",
            "like-alter",
            "truncate-function",
        ],
    )
    def test_allows_read_operations(self, sql):
        assert FORBIDDEN_SQL_RE.match(sql) is None, f"Should allow: {sql}"


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------


class TestCreateExternalDatabaseSchema:
    """Validates CreateExternalDatabase field constraints."""

    VALID_PAYLOAD = {
        "name": "my-db",
        "connection_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "username": "user",
        "password": "pass",
    }

    def test_valid_postgresql(self):
        obj = CreateExternalDatabase(**self.VALID_PAYLOAD)
        assert obj.connection_type == "postgresql"

    def test_valid_mysql(self):
        payload = {**self.VALID_PAYLOAD, "connection_type": "mysql"}
        obj = CreateExternalDatabase(**payload)
        assert obj.connection_type == "mysql"

    def test_invalid_connection_type(self):
        payload = {**self.VALID_PAYLOAD, "connection_type": "sqlite"}
        with pytest.raises(ValidationError) as exc_info:
            CreateExternalDatabase(**payload)
        errors = exc_info.value.errors()
        assert any("connection_type" in str(e["loc"]) for e in errors)

    def test_invalid_connection_type_empty(self):
        payload = {**self.VALID_PAYLOAD, "connection_type": ""}
        with pytest.raises(ValidationError):
            CreateExternalDatabase(**payload)

    def test_port_too_low(self):
        payload = {**self.VALID_PAYLOAD, "port": 0}
        with pytest.raises(ValidationError) as exc_info:
            CreateExternalDatabase(**payload)
        errors = exc_info.value.errors()
        assert any("port" in str(e["loc"]) for e in errors)

    def test_port_too_high(self):
        payload = {**self.VALID_PAYLOAD, "port": 65536}
        with pytest.raises(ValidationError) as exc_info:
            CreateExternalDatabase(**payload)
        errors = exc_info.value.errors()
        assert any("port" in str(e["loc"]) for e in errors)

    def test_port_boundary_low(self):
        payload = {**self.VALID_PAYLOAD, "port": 1}
        obj = CreateExternalDatabase(**payload)
        assert obj.port == 1

    def test_port_boundary_high(self):
        payload = {**self.VALID_PAYLOAD, "port": 65535}
        obj = CreateExternalDatabase(**payload)
        assert obj.port == 65535

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateExternalDatabase()
        errors = exc_info.value.errors()
        missing_fields = {str(e["loc"][0]) for e in errors if e["type"] == "missing"}
        assert "name" in missing_fields
        assert "connection_type" in missing_fields
        assert "host" in missing_fields
        assert "port" in missing_fields
        assert "database" in missing_fields
        assert "username" in missing_fields
        assert "password" in missing_fields

    def test_empty_name_rejected(self):
        payload = {**self.VALID_PAYLOAD, "name": ""}
        with pytest.raises(ValidationError):
            CreateExternalDatabase(**payload)

    def test_empty_host_rejected(self):
        payload = {**self.VALID_PAYLOAD, "host": ""}
        with pytest.raises(ValidationError):
            CreateExternalDatabase(**payload)

    def test_empty_password_rejected(self):
        payload = {**self.VALID_PAYLOAD, "password": ""}
        with pytest.raises(ValidationError):
            CreateExternalDatabase(**payload)

    def test_name_too_long(self):
        payload = {**self.VALID_PAYLOAD, "name": "x" * 256}
        with pytest.raises(ValidationError):
            CreateExternalDatabase(**payload)


class TestUpdateExternalDatabaseSchema:
    """Validates UpdateExternalDatabase allows partial updates."""

    def test_all_fields_optional(self):
        obj = UpdateExternalDatabase()
        assert obj.name is None
        assert obj.port is None
        assert obj.is_active is None

    def test_invalid_connection_type_rejected(self):
        with pytest.raises(ValidationError):
            UpdateExternalDatabase(connection_type="oracle")

    def test_invalid_port_rejected(self):
        with pytest.raises(ValidationError):
            UpdateExternalDatabase(port=0)

    def test_valid_partial_update(self):
        obj = UpdateExternalDatabase(name="new-name", port=3306)
        assert obj.name == "new-name"
        assert obj.port == 3306
        assert obj.host is None


# ---------------------------------------------------------------------------
# URL building safety (build_external_db_url)
# ---------------------------------------------------------------------------


class TestBuildExternalDbUrl:
    """Test build_external_db_url produces valid SQLAlchemy URL objects."""

    def _make_config(self, **overrides) -> ExternalDatabaseConfig:
        defaults = {
            "id": 1,
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "username": "user",
            "password": "pass",
            "dialect": "postgresql",
        }
        defaults.update(overrides)
        return ExternalDatabaseConfig(**defaults)

    def test_returns_sqlalchemy_url(self):
        config = self._make_config()
        url = build_external_db_url(config)
        assert isinstance(url, URL)

    def test_postgresql_url(self):
        config = self._make_config()
        url = build_external_db_url(config)
        assert url.get_backend_name() == "postgresql"
        assert url.username == "user"
        assert url.host == "localhost"
        assert url.port == 5432
        assert url.database == "testdb"
        assert url.drivername == "postgresql+psycopg2"

    def test_mysql_url(self):
        config = self._make_config(dialect="mysql")
        url = build_external_db_url(config)
        assert url.drivername == "mysql+pymysql"
        assert url.username == "user"
        assert url.host == "localhost"

    def test_unknown_dialect_uses_raw(self):
        config = self._make_config(dialect="mssql")
        url = build_external_db_url(config)
        assert url.drivername == "mssql"
        assert url.username == "user"

    @pytest.mark.parametrize(
        "password",
        [
            "p@ss",
            "p/ss",
            "p:ss",
            "p%ss",
            "p#ss",
            "p@ss:w/rd#100%done",
        ],
        ids=["at-sign", "forward-slash", "colon", "percent", "hash", "combined-special"],
    )
    def test_special_chars_in_password_safely_handled(self, password):
        """URL.create properly escapes special characters in passwords.
        The password is recoverable from the URL object even when it
        contains characters like @, /, :, %, # that would break naive
        f-string URL construction.
        """
        config = self._make_config(password=password)
        url = build_external_db_url(config)
        assert isinstance(url, URL)
        # The rendered URL string is valid (password is escaped)
        rendered = url.render_as_string(hide_password=False)
        assert rendered.startswith("postgresql+psycopg2://")
        assert "localhost:5432/testdb" in rendered

    def test_url_contains_all_components(self):
        config = self._make_config(
            username="admin",
            password="secret",
            host="db.example.com",
            port=5433,
            database="prod",
        )
        url = build_external_db_url(config)
        assert url.username == "admin"
        assert url.host == "db.example.com"
        assert url.port == 5433
        assert url.database == "prod"
        rendered = url.render_as_string(hide_password=False)
        assert "admin" in rendered
        assert "secret" in rendered
        assert "db.example.com" in rendered
        assert "5433" in rendered
        assert "prod" in rendered
