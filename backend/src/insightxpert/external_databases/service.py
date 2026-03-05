import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from insightxpert.auth.encryption import decrypt_credentials, encrypt_credentials
from insightxpert.auth.models import ExternalDatabaseConnection, UserDatabaseConnection, _uuid, _utcnow
from insightxpert.db.introspector import get_introspector

_logger = logging.getLogger(__name__)


class ExternalDatabaseService:
    def __init__(self, engine):
        self._engine = engine

    def _decrypt_password(self, encrypted_password: str) -> str:
        try:
            return decrypt_credentials(encrypted_password)
        except Exception:
            _logger.error("Failed to decrypt external database password — is ENCRYPTION_KEY set correctly?")
            raise

    def _to_response(self, db: ExternalDatabaseConnection) -> dict:
        return {
            "id": db.id,
            "name": db.name,
            "connection_type": db.connection_type,
            "host": db.host,
            "port": db.port,
            "database": db.database,
            "username": db.username,
            "is_active": db.is_active,
            "is_verified": db.is_verified,
            "last_verified_at": db.last_verified_at,
            "created_at": db.created_at,
            "updated_at": db.updated_at,
        }

    def create_external_database(
        self,
        name: str,
        connection_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        organization_id: Optional[str] = None,
    ) -> dict:
        encrypted_password = encrypt_credentials(password)
        now = _utcnow()

        with Session(self._engine) as session:
            db = ExternalDatabaseConnection(
                id=_uuid(),
                organization_id=organization_id,
                name=name,
                connection_type=connection_type,
                host=host,
                port=port,
                database=database,
                username=username,
                password=encrypted_password,
                is_active=False,
                is_verified=False,
                last_verified_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(db)
            session.commit()
            session.refresh(db)
            return self._to_response(db)

    def get_external_databases(self, organization_id: Optional[str]) -> list[dict]:
        with Session(self._engine) as session:
            query = session.query(ExternalDatabaseConnection)
            if organization_id:
                query = query.filter(
                    ExternalDatabaseConnection.organization_id == organization_id
                )
            dbs = query.order_by(ExternalDatabaseConnection.created_at.desc()).all()
            return [self._to_response(db) for db in dbs]

    def get_active_external_database(
        self, organization_id: Optional[str]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            query = session.query(ExternalDatabaseConnection).filter(
                ExternalDatabaseConnection.is_active.is_(True),
                ExternalDatabaseConnection.is_verified.is_(True),
            )
            if organization_id:
                query = query.filter(
                    ExternalDatabaseConnection.organization_id == organization_id
                )
            db = query.first()
            return self._to_response(db) if db else None

    def get_external_database(
        self, db_id: str, organization_id: Optional[str]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            db = session.get(ExternalDatabaseConnection, db_id)
            if not db:
                return None
            if organization_id and db.organization_id != organization_id:
                return None
            return self._to_response(db)

    def update_external_database(
        self,
        db_id: str,
        organization_id: Optional[str],
        name: Optional[str] = None,
        connection_type: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            db = session.get(ExternalDatabaseConnection, db_id)
            if not db:
                return None
            if organization_id and db.organization_id != organization_id:
                return None

            if is_active is True:
                session.query(ExternalDatabaseConnection).filter(
                    ExternalDatabaseConnection.organization_id == organization_id,
                    ExternalDatabaseConnection.id != db_id,
                ).update({"is_active": False})

            if name is not None:
                db.name = name
            if connection_type is not None:
                db.connection_type = connection_type
            if host is not None:
                db.host = host
            if port is not None:
                db.port = port
            if database is not None:
                db.database = database
            if username is not None:
                db.username = username
            if password is not None:
                db.password = encrypt_credentials(password)
            if is_active is not None:
                db.is_active = is_active

            db.updated_at = _utcnow()
            session.commit()
            session.refresh(db)
            return self._to_response(db)

    def delete_external_database(
        self, db_id: str, organization_id: Optional[str]
    ) -> bool:
        with Session(self._engine) as session:
            db = session.get(ExternalDatabaseConnection, db_id)
            if not db:
                return False
            if organization_id and db.organization_id != organization_id:
                return False
            session.delete(db)
            session.commit()
            return True

    async def test_connection(
        self, db_id: str, organization_id: Optional[str]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            db = session.get(ExternalDatabaseConnection, db_id)
            if not db:
                return None
            if organization_id and db.organization_id != organization_id:
                return None
            db_data = {
                "host": db.host,
                "port": db.port,
                "database": db.database,
                "username": db.username,
                "password": self._decrypt_password(db.password),
                "connection_type": db.connection_type,
            }

        introspector = await get_introspector(**db_data)

        success = await asyncio.to_thread(introspector.test_connection)
        table_count = None

        if success:
            try:
                tables = await asyncio.to_thread(introspector.get_tables)
                table_count = len(tables)
            except Exception:
                pass

            now = datetime.now(timezone.utc)
            with Session(self._engine) as session:
                db = session.get(ExternalDatabaseConnection, db_id)
                if db:
                    db.is_verified = True
                    db.last_verified_at = now
                    db.updated_at = now
                    session.commit()

        await asyncio.to_thread(introspector.disconnect)

        return {
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
            "table_count": table_count,
        }

    async def refresh_schema(
        self,
        db_id: str,
        organization_id: Optional[str],
        rag_store,
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            db = session.get(ExternalDatabaseConnection, db_id)
            if not db:
                return None
            if organization_id and db.organization_id != organization_id:
                return None
            db_data = {
                "host": db.host,
                "port": db.port,
                "database": db.database,
                "username": db.username,
                "password": self._decrypt_password(db.password),
                "connection_type": db.connection_type,
            }

        introspector = await get_introspector(**db_data)

        test_ok = await asyncio.to_thread(introspector.test_connection)
        if not test_ok:
            await asyncio.to_thread(introspector.disconnect)
            return {
                "success": False,
                "message": "Connection test failed",
                "table_count": 0,
            }

        try:
            schema_info = await asyncio.to_thread(introspector.get_schema)
        except Exception as e:
            await asyncio.to_thread(introspector.disconnect)
            return {
                "success": False,
                "message": f"Failed to introspect schema: {str(e)}",
                "table_count": 0,
            }

        ddl_statements = []
        for table in schema_info.tables:
            cols = []
            for col in table.columns:
                col_def = f"{col.name} {col.data_type}"
                if not col.is_nullable:
                    col_def += " NOT NULL"
                if col.default_value:
                    col_def += f" DEFAULT {col.default_value}"
                if col.is_primary_key:
                    col_def += " PRIMARY KEY"
                cols.append(col_def)

            fk_statements = []
            fks = await asyncio.to_thread(introspector.get_foreign_keys, table.name)
            for fk in fks:
                fk_statements.append(
                    f"ALTER TABLE {table.name} ADD FOREIGN KEY ({fk.column_name}) "
                    f"REFERENCES {fk.referenced_table}({fk.referenced_column});"
                )

            ddl = f"CREATE TABLE {table.name} (\n  " + ",\n  ".join(cols) + "\n);"
            if fk_statements:
                ddl += "\n\n" + "\n".join(fk_statements)

            metadata = {
                "dataset_id": None,
                "org_id": organization_id,
                "source": "external_db",
                "external_db_id": db_id,
                "table_name": table.name,
            }
            rag_store.add_ddl(ddl, table_name=table.name, metadata=metadata)
            ddl_statements.append(ddl)

        await asyncio.to_thread(introspector.disconnect)

        return {
            "success": True,
            "message": f"Schema refreshed: {len(ddl_statements)} tables",
            "table_count": len(ddl_statements),
        }


class UserDatabaseService:
    """Service for user-scoped database connections.

    Stores the full connection string (encrypted). Display fields are parsed
    from the DSN on read — the raw connection string is never returned.
    """

    def __init__(self, engine):
        self._engine = engine

    @staticmethod
    def _parse_dsn(dsn: str) -> dict:
        """Extract display fields from a PostgreSQL DSN."""
        parsed = urlparse(dsn)
        return {
            "host": parsed.hostname or "",
            "port": parsed.port or 5432,
            "database": (parsed.path or "").lstrip("/"),
            "username": parsed.username or "",
            "password": parsed.password or "",
        }

    def _to_response(self, conn: UserDatabaseConnection) -> dict:
        """Build a response dict — never includes the raw connection string."""
        try:
            dsn = decrypt_credentials(conn.connection_string)
            parts = self._parse_dsn(dsn)
        except Exception:
            parts = {"host": None, "port": None, "database": None, "username": None}

        return {
            "id": conn.id,
            "name": conn.name,
            "host": parts.get("host"),
            "port": parts.get("port"),
            "database": parts.get("database"),
            "username": parts.get("username"),
            "is_active": conn.is_active,
            "is_verified": conn.is_verified,
            "last_verified_at": conn.last_verified_at,
            "created_at": conn.created_at,
            "updated_at": conn.updated_at,
        }

    def create_connection(self, user_id: str, name: str, connection_string: str) -> dict:
        encrypted = encrypt_credentials(connection_string)
        now = _utcnow()

        with Session(self._engine) as session:
            conn = UserDatabaseConnection(
                id=_uuid(),
                user_id=user_id,
                name=name,
                connection_string=encrypted,
                is_active=False,
                is_verified=False,
                last_verified_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(conn)
            session.commit()
            session.refresh(conn)
            return self._to_response(conn)

    def list_connections(self, user_id: str) -> list[dict]:
        with Session(self._engine) as session:
            conns = (
                session.query(UserDatabaseConnection)
                .filter(UserDatabaseConnection.user_id == user_id)
                .order_by(UserDatabaseConnection.created_at.desc())
                .all()
            )
            return [self._to_response(c) for c in conns]

    def delete_connection(self, conn_id: str, user_id: str) -> bool:
        with Session(self._engine) as session:
            conn = session.get(UserDatabaseConnection, conn_id)
            if not conn or conn.user_id != user_id:
                return False
            session.delete(conn)
            session.commit()
            return True

    def set_active(self, conn_id: str, user_id: str, active: bool) -> Optional[dict]:
        with Session(self._engine) as session:
            conn = session.get(UserDatabaseConnection, conn_id)
            if not conn or conn.user_id != user_id:
                return None

            if active:
                # Deactivate all other connections for this user atomically
                session.query(UserDatabaseConnection).filter(
                    UserDatabaseConnection.user_id == user_id,
                    UserDatabaseConnection.id != conn_id,
                ).update({"is_active": False})

            conn.is_active = active
            conn.updated_at = _utcnow()
            session.commit()
            session.refresh(conn)
            return self._to_response(conn)

    def get_active_connection(self, user_id: str) -> Optional[dict]:
        """Return the active connection for agent use (includes decrypted parsed fields)."""
        with Session(self._engine) as session:
            conn = (
                session.query(UserDatabaseConnection)
                .filter(
                    UserDatabaseConnection.user_id == user_id,
                    UserDatabaseConnection.is_active.is_(True),
                    UserDatabaseConnection.is_verified.is_(True),
                )
                .first()
            )
            if not conn:
                return None

            dsn = decrypt_credentials(conn.connection_string)
            parts = self._parse_dsn(dsn)
            return {
                "id": conn.id,
                "name": conn.name,
                "host": parts["host"],
                "port": parts["port"],
                "database": parts["database"],
                "username": parts["username"],
                "password": parts["password"],
                "connection_type": "postgresql",
            }

    async def test_connection(self, conn_id: str, user_id: str) -> Optional[dict]:
        with Session(self._engine) as session:
            conn = session.get(UserDatabaseConnection, conn_id)
            if not conn or conn.user_id != user_id:
                return None
            dsn = decrypt_credentials(conn.connection_string)
            parts = self._parse_dsn(dsn)
            db_data = {
                "host": parts["host"],
                "port": parts["port"],
                "database": parts["database"],
                "username": parts["username"],
                "password": parts["password"],
                "connection_type": "postgresql",
            }

        introspector = await get_introspector(**db_data)
        success = await asyncio.to_thread(introspector.test_connection)
        table_count = None

        if success:
            try:
                tables = await asyncio.to_thread(introspector.get_tables)
                table_count = len(tables)
            except Exception:
                pass

            now = datetime.now(timezone.utc)
            with Session(self._engine) as session:
                conn = session.get(UserDatabaseConnection, conn_id)
                if conn:
                    conn.is_verified = True
                    conn.last_verified_at = now
                    conn.updated_at = now
                    session.commit()

        await asyncio.to_thread(introspector.disconnect)

        return {
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
            "table_count": table_count,
        }
