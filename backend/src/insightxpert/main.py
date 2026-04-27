from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from insightxpert.admin.config_store import migrate_from_json
from insightxpert.admin.routes import router as admin_router
from insightxpert.api.routes import router
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.models import Base as AuthBase
from insightxpert.auth.routes import router as auth_router
from insightxpert.auth.seed import seed_admin
from insightxpert.config import Settings
from insightxpert.exceptions import InsightXpertError
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.factory import create_llm
from insightxpert.memory.conversation_store import ConversationStore
from insightxpert.rag.store import VectorStore
from insightxpert.training.trainer import Trainer

logger = logging.getLogger("insightxpert")


def _migrate_schema(engine) -> None:
    """Add new columns to existing tables (idempotent, no Alembic needed)."""
    from insightxpert.db.migrations import MIGRATION_COLUMNS, SCHEMA_INDEXES

    insp = inspect(engine)
    dialect = engine.dialect.name

    existing_tables = set(insp.get_table_names())

    with engine.begin() as conn:
        def _add_column(table: str, column: str, col_def: str) -> None:
            if table not in existing_tables:
                return
            cols = {c["name"] for c in insp.get_columns(table)}
            if column in cols:
                return
            if dialect == "postgresql":
                sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_def}"
            else:
                sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
            try:
                conn.execute(text(sql))
                logger.info("Migration: added %s.%s", table, column)
            except Exception:
                logger.debug("Column %s.%s already exists (dialect=%s)", table, column, dialect)

        # PostgreSQL uses different boolean syntax
        pg_overrides = {
            ("users", "is_admin"): "BOOLEAN DEFAULT FALSE NOT NULL",
            ("conversations", "is_starred"): "BOOLEAN DEFAULT FALSE NOT NULL",
        }

        for table, column, col_def in MIGRATION_COLUMNS:
            if dialect == "postgresql" and (table, column) in pg_overrides:
                col_def = pg_overrides[(table, column)]
            _add_column(table, column, col_def)

        # Backfill updated_at = created_at for existing rows that don't have it
        conn.execute(text(
            "UPDATE users SET updated_at = created_at WHERE updated_at IS NULL"
        ))

        for idx_sql in SCHEMA_INDEXES:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.debug("Index creation skipped: %s", e)

        # Transaction timestamp index (table may not exist yet at migration time)
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON transactions (timestamp)"
            ))
        except Exception:
            logger.debug("transactions table not present yet, skipping idx_timestamp")

        # Drop legacy tables
        existing_tables = set(insp.get_table_names())
        if "feedback" in existing_tables:
            conn.execute(text("DROP TABLE feedback"))
            logger.info("Migration: dropped feedback table")
        if "alembic_version" in existing_tables:
            conn.execute(text("DROP TABLE alembic_version"))
            logger.info("Migration: dropped alembic_version table")


def _migrate_trigger_conditions(engine) -> None:
    """Migrate trigger_conditions JSON blobs into normalized automation_triggers rows.

    Idempotent: skips automations that already have rows in automation_triggers.
    """
    import json as _json
    from insightxpert.auth.models import AutomationTrigger, _uuid, _utcnow

    with Session(engine) as session:
        rows = (
            session.execute(
                text(
                    "SELECT id, trigger_conditions FROM automations "
                    "WHERE trigger_conditions IS NOT NULL AND trigger_conditions != '[]'"
                )
            ).fetchall()
        )
        migrated = 0
        for auto_id, tc_json in rows:
            # Skip if already migrated
            existing = (
                session.query(AutomationTrigger)
                .filter(AutomationTrigger.automation_id == auto_id)
                .first()
            )
            if existing:
                continue

            try:
                conditions = _json.loads(tc_json)
            except (ValueError, TypeError):
                continue

            if not isinstance(conditions, list):
                continue

            now = _utcnow()
            for i, cond in enumerate(conditions):
                session.add(AutomationTrigger(
                    id=_uuid(),
                    automation_id=auto_id,
                    ordinal_position=i,
                    type=cond.get("type", "threshold"),
                    column=cond.get("column"),
                    operator=cond.get("operator"),
                    value=cond.get("value"),
                    change_percent=cond.get("change_percent"),
                    scope=cond.get("scope"),
                    slope_window=cond.get("slope_window"),
                    nl_text=cond.get("nl_text"),
                    created_at=now,
                    updated_at=now,
                ))
            migrated += 1

        if migrated:
            session.commit()
            logger.info("Migrated trigger conditions for %d automations", migrated)
        else:
            logger.debug("No trigger conditions to migrate")


def _backfill_conversation_org(engine) -> None:
    """Stamp conversations.org_id from their owner's users.org_id (idempotent).

    User-to-org assignments are managed via the admin panel.  This only
    propagates the existing users.org_id onto conversations that were
    created before the org_id column existed.
    """
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE conversations SET org_id = ("
            "  SELECT users.org_id FROM users WHERE users.id = conversations.user_id"
            ") WHERE conversations.org_id IS NULL"
            "  AND EXISTS ("
            "    SELECT 1 FROM users"
            "    WHERE users.id = conversations.user_id AND users.org_id IS NOT NULL"
            "  )"
        ))
        if result.rowcount:
            logger.info("Backfilled org_id on %d conversations", result.rowcount)


def _backfill_automation_org(engine) -> None:
    """Stamp automations.org_id and trigger_templates.org_id from creator's users.org_id."""
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE automations SET org_id = ("
            "  SELECT users.org_id FROM users WHERE users.id = automations.created_by"
            ") WHERE automations.org_id IS NULL"
            "  AND EXISTS ("
            "    SELECT 1 FROM users"
            "    WHERE users.id = automations.created_by AND users.org_id IS NOT NULL"
            "  )"
        ))
        if result.rowcount:
            logger.info("Backfilled org_id on %d automations", result.rowcount)

        result2 = conn.execute(text(
            "UPDATE trigger_templates SET org_id = ("
            "  SELECT users.org_id FROM users WHERE users.id = trigger_templates.created_by"
            ") WHERE trigger_templates.org_id IS NULL"
            "  AND EXISTS ("
            "    SELECT 1 FROM users"
            "    WHERE users.id = trigger_templates.created_by AND users.org_id IS NOT NULL"
            "  )"
        ))
        if result2.rowcount:
            logger.info("Backfilled org_id on %d trigger_templates", result2.rowcount)


def _seed_datasets(engine) -> None:
    """Seed the datasets, dataset_columns, and example_queries tables from hardcoded training data."""
    from insightxpert.auth.models import Dataset, DatasetColumn, ExampleQuery, _uuid, _utcnow
    from insightxpert.training.documentation import DOCUMENTATION
    from insightxpert.training.queries import EXAMPLE_QUERIES
    from insightxpert.training.schema import DDL
    from insightxpert.training.seed_data import COLUMNS_META

    with Session(engine) as session:
        existing = session.query(Dataset).first()
        if existing:
            logger.debug("Datasets already seeded, skipping")
            return

        now = _utcnow()
        dataset_id = _uuid()

        dataset = Dataset(
            id=dataset_id,
            name="transactions",
            description="250,000 Indian UPI digital payment transactions from 2024",
            ddl=DDL,
            documentation=DOCUMENTATION,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(dataset)

        for i, col in enumerate(COLUMNS_META):
            session.add(DatasetColumn(
                id=_uuid(),
                dataset_id=dataset_id,
                column_name=col["column_name"],
                column_type=col["column_type"],
                description=col["description"],
                domain_values=col["domain_values"],
                domain_rules=col["domain_rules"],
                ordinal_position=i,
                created_at=now,
            ))

        for qa in EXAMPLE_QUERIES:
            session.add(ExampleQuery(
                id=_uuid(),
                dataset_id=dataset_id,
                question=qa["question"],
                sql=qa["sql"],
                category=qa.get("category"),
                is_active=True,
                created_at=now,
            ))

        session.commit()
        logger.info(
            "Seeded dataset '%s': %d columns, %d example queries",
            "transactions", len(COLUMNS_META), len(EXAMPLE_QUERIES),
        )


def _seed_prompts(engine) -> None:
    """Seed missing prompt templates from .j2 files (per-template, idempotent)."""
    from insightxpert.auth.models import PromptTemplate, _uuid, _utcnow
    from insightxpert.prompts import get_file_content

    templates = [
        ("analyst_system", "analyst_system.j2", "System prompt for the SQL analyst agent"),
        ("statistician_system", "statistician_system.j2", "System prompt for the statistician agent"),
        ("advanced_system", "advanced_system.j2", "System prompt for the advanced analytics agent"),
    ]
    with Session(engine) as session:
        seeded = 0
        for name, filename, description in templates:
            existing = session.query(PromptTemplate).filter_by(name=name).first()
            try:
                content = get_file_content(filename)
            except FileNotFoundError:
                logger.warning("Template file not found: %s", filename)
                continue
            if existing:
                # Update stale DB prompts that predate the clarification feature
                if "clarification_enabled" not in (existing.content or ""):
                    existing.content = content
                    existing.updated_at = _utcnow()
                    seeded += 1
                    logger.info("Updated prompt template: %s (added clarification block)", name)
                continue
            prompt = PromptTemplate(
                id=_uuid(),
                name=name,
                content=content,
                description=description,
                is_active=True,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(prompt)
            seeded += 1
            logger.info("Seeded prompt template: %s", name)
        session.commit()
        if seeded == 0:
            logger.debug("All prompt templates already seeded")


def _setup_logging(level: str) -> None:
    root = logging.getLogger("insightxpert")
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "\033[90m%(asctime)s\033[0m %(levelname)-5s \033[36m%(name)s\033[0m  %(message)s",
            datefmt="%H:%M:%S",
        ))
        root.addHandler(handler)
    # Quiet down noisy libraries
    for lib in ("chromadb", "httpcore", "httpx", "urllib3", "sqlalchemy.engine"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def _run_rag_training(rag: VectorStore, db: DatabaseConnector, dataset_service=None) -> None:
    """Run RAG training in a background thread (called via asyncio.to_thread)."""
    trainer = Trainer(rag)
    try:
        count = trainer.train_insightxpert(db, dataset_service=dataset_service)
        logger.info("RAG bootstrap complete: %d training items loaded", count)
    except Exception as e:
        logger.error("RAG bootstrap failed: %s", e, exc_info=True)


_TRANSACTIONS_MIN_EXPECTED = 200_000


def _ensure_transactions_loaded(db: DatabaseConnector) -> None:
    """Load transactions from CSV if table is empty/sparse and seeding is allowed.

    Skips entirely when:
      - INSIGHTXPERT_SKIP_SEED is truthy (production safety against accidental
        re-seeds against Turso primary).
      - Connector is libSQL/Turso. The remote primary is the source of truth
        and already holds the canonical 250K rows; seeding from a Cloud Run
        instance over the network would be slow and would risk duplicating or
        overwriting live data.
      - Table already has >= _TRANSACTIONS_MIN_EXPECTED rows.
    """
    if os.environ.get("INSIGHTXPERT_SKIP_SEED", "").lower() in {"1", "true", "yes"}:
        logger.info("INSIGHTXPERT_SKIP_SEED set — skipping transactions seed")
        return

    if db.is_libsql:
        logger.info("Connector is libSQL/Turso — skipping CSV seed (remote primary is canonical)")
        return

    engine = db.engine
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)

    if "transactions" in insp.get_table_names():
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar() or 0
            if count >= _TRANSACTIONS_MIN_EXPECTED:
                logger.debug("transactions table already has %d rows, skipping CSV load", count)
                return
            if count > 0:
                logger.warning(
                    "transactions has %d rows (< %d expected); refusing to auto-seed over partial data — "
                    "set INSIGHTXPERT_SKIP_SEED=0 and manually clear the table to re-seed",
                    count, _TRANSACTIONS_MIN_EXPECTED,
                )
                return

    # Find the CSV file relative to the backend directory
    csv_candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "upi_transactions_2024.csv",
        Path("upi_transactions_2024.csv"),
        Path("backend/upi_transactions_2024.csv"),
    ]

    csv_path = None
    for candidate in csv_candidates:
        if candidate.exists():
            csv_path = candidate
            break

    if csv_path is None:
        logger.warning("No CSV file found for transactions table — queries will fail until data is loaded")
        return

    from insightxpert.db.data_loader import load_data
    db_url = str(engine.url)
    logger.info("Loading transactions from %s into local SQLite...", csv_path)
    count = load_data(source=csv_path, table="transactions", db_url=db_url, if_exists="append")
    logger.info("Loaded %d transactions from CSV", count)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = _settings
    _setup_logging(settings.log_level)

    logger.info("Starting InsightXpert (log_level=%s)", settings.log_level)

    # 1. Connect to database (local SQLite for dev, Turso libSQL embedded replica for prod)
    db = DatabaseConnector()
    try:
        db.connect(
            settings.database_url,
            turso_auth_token=settings.turso_auth_token,
            turso_local_replica_path=settings.turso_local_replica_path,
            turso_sync_interval_seconds=settings.turso_sync_interval_seconds,
        )
        safe_url = db.engine.url.render_as_string(hide_password=True)
        logger.info("Database connected: %s (libsql=%s)", safe_url, db.is_libsql)
    except Exception as e:
        logger.error("Database connection failed: %s", e, exc_info=True)
        raise

    auth_engine = db.engine

    # 2. Create auth tables, run migrations, and seed admin user
    try:
        AuthBase.metadata.create_all(auth_engine)
        _migrate_schema(auth_engine)
        _migrate_trigger_conditions(auth_engine)
        seed_admin(auth_engine, settings)
        _backfill_conversation_org(auth_engine)
        _backfill_automation_org(auth_engine)
        logger.info("Auth tables initialized, admin user ensured")
    except Exception as e:
        logger.error("Auth table setup failed: %s", e, exc_info=True)

    # 3. Seed prompts, datasets (idempotent)
    try:
        _seed_prompts(auth_engine)
        logger.info("Prompt templates initialized")
    except Exception as e:
        logger.error("Prompt seeding failed: %s", e, exc_info=True)

    try:
        _seed_datasets(auth_engine)
        logger.info("Dataset tables initialized")
    except Exception as e:
        logger.error("Dataset seeding failed: %s", e, exc_info=True)

    # 5. Load transactions from CSV if not already present
    try:
        await asyncio.to_thread(_ensure_transactions_loaded, db)
    except Exception as e:
        logger.error("Transaction loading failed: %s", e, exc_info=True)

    # 6. Pre-compute dataset statistics (idempotent)
    try:
        from insightxpert.db.stats_computer import compute_and_store_stats
        n = await asyncio.to_thread(compute_and_store_stats, auth_engine)
        if n:
            logger.info("Dataset stats computed: %d rows written", n)
        else:
            logger.debug("Dataset stats already present, skipping computation")
    except Exception as e:
        logger.error("Dataset stats computation failed: %s", e, exc_info=True)

    # RAG vector store
    rag = VectorStore(persist_dir=settings.chroma_persist_dir)
    logger.info("ChromaDB initialized: %s", settings.chroma_persist_dir)

    # LLM provider
    llm = create_llm(settings.llm_provider.value, settings)
    logger.info("LLM provider: %s", settings.llm_provider.value)

    # Dataset service
    from insightxpert.datasets.service import DatasetService
    dataset_service = DatasetService(auth_engine)

    # Bootstrap RAG in a background thread (after dataset tables are seeded)
    rag_task = asyncio.create_task(
        asyncio.to_thread(_run_rag_training, rag, db, dataset_service)
    )

    # Persistent conversation store (SQLite-backed)
    persistent_conv_store = PersistentConversationStore(auth_engine)
    logger.info("Persistent conversation store initialized")

    # Conversation memory (in-memory for LLM context)
    conversation_store = ConversationStore(ttl_seconds=settings.conversation_ttl_seconds)
    logger.info("Conversation memory initialized (in-memory)")

    # Store on app state
    app.state.settings = settings
    app.state.db = db
    app.state.rag = rag
    app.state.llm = llm
    app.state.conversation_store = conversation_store
    app.state.auth_engine = auth_engine
    app.state.persistent_conv_store = persistent_conv_store
    app.state.dataset_service = dataset_service

    # Automation service + scheduler
    from insightxpert.automations.service import AutomationService
    from insightxpert.automations.scheduler import AutomationScheduler
    app.state.automation_service = AutomationService(auth_engine)
    automation_scheduler = AutomationScheduler(auth_engine, db)
    try:
        await automation_scheduler.start()
        app.state.automation_scheduler = automation_scheduler
        logger.info("Automation scheduler initialized")
    except Exception as e:
        logger.error("Automation scheduler startup failed: %s", e, exc_info=True)

    # Admin config — stored in the DB; migrate from legacy JSON file if needed
    legacy_config_path = Path(__file__).resolve().parent.parent.parent / "config" / "client-configs.json"
    try:
        migrate_from_json(auth_engine, legacy_config_path)
        logger.info("Admin config ready (DB-backed)")
    except Exception as e:
        logger.error("Admin config migration failed: %s", e, exc_info=True)

    # Wait for RAG training to finish (with timeout so server still starts)
    rag_timeout = settings.rag_bootstrap_timeout_seconds
    try:
        await asyncio.wait_for(rag_task, timeout=rag_timeout)
    except asyncio.TimeoutError:
        logger.warning("RAG training still running after %ds, continuing startup", rag_timeout)
    except Exception as e:
        logger.error("RAG training error: %s", e, exc_info=True)

    # Periodic cleanup of unconfirmed (orphan) uploaded datasets
    async def _orphan_cleanup_loop():
        # Run once shortly after startup, then every 15 minutes
        await asyncio.sleep(60)
        while True:
            try:
                cleaned = await asyncio.to_thread(
                    dataset_service.cleanup_stale_unconfirmed, 30,
                )
                if cleaned:
                    logger.info("Orphan cleanup: removed %d stale datasets", cleaned)
            except Exception as e:
                logger.warning("Orphan cleanup error: %s", e, exc_info=True)
            await asyncio.sleep(15 * 60)

    orphan_cleanup_task = asyncio.create_task(_orphan_cleanup_loop())

    logger.info("InsightXpert ready")
    yield

    # Shutdown
    orphan_cleanup_task.cancel()
    if hasattr(app.state, 'automation_scheduler'):
        await app.state.automation_scheduler.shutdown()
    if not rag_task.done():
        rag_task.cancel()
    db.disconnect()
    logger.info("Shutdown complete")


app = FastAPI(title="InsightXpert", version="0.1.0", lifespan=lifespan)

_settings = Settings()
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(InsightXpertError)
async def insightxpert_error_handler(_request: Request, exc: InsightXpertError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "detail": exc.message,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    field_errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        field_errors.append(f"{loc}: {err.get('msg', 'invalid')}")
    return JSONResponse(
        status_code=400,
        content={
            "error": "VALIDATION_ERROR",
            "detail": "; ".join(field_errors),
            "status_code": 400,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    logger.debug("Full traceback:\n%s", traceback.format_exc())

    # Starlette's ServerErrorMiddleware (outermost) can intercept generic
    # exception handler responses before CORSMiddleware adds headers.
    # Manually attach CORS headers so browsers can read 500 error bodies.
    headers: dict[str, str] = {}
    origin = request.headers.get("origin", "")
    if origin:
        allowed = [o.strip() for o in _settings.cors_origins.split(",")]
        if origin in allowed:
            headers["access-control-allow-origin"] = origin
            headers["access-control-allow-credentials"] = "true"
            headers["vary"] = "Origin"

    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "detail": "An unexpected internal error occurred",
            "status_code": 500,
        },
        headers=headers,
    )


@app.get("/health")
@app.get("/api/health")
async def health_check():
    return JSONResponse({"status": "ok"})


from insightxpert.datasets.routes import router as datasets_router
from insightxpert.automations.routes import router as automations_router, notifications_router, templates_router
from insightxpert.insights.routes import router as insights_router
from insightxpert.voice.routes import router as voice_router

app.include_router(router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(datasets_router)
app.include_router(automations_router)
app.include_router(notifications_router)
app.include_router(templates_router)
app.include_router(insights_router)
app.include_router(voice_router)

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("insightxpert.main:app", host="0.0.0.0", port=port, reload=True)
