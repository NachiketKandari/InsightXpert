from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path

from insightxpert.admin.config_store import read_config, write_config
from insightxpert.admin.routes import router as admin_router
from insightxpert.api.routes import router
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.models import Base as AuthBase
from insightxpert.auth.routes import router as auth_router
from insightxpert.auth.seed import seed_admin
from insightxpert.config import Settings
from insightxpert.llm.factory import create_llm
from insightxpert.db.connector import DatabaseConnector
from insightxpert.memory.conversation_store import ConversationStore
from insightxpert.rag.store import VectorStore
from insightxpert.training.trainer import Trainer

from sqlalchemy import inspect, text

logger = logging.getLogger("insightxpert")


def _migrate_schema(engine) -> None:
    """Add new columns to existing tables (idempotent, no Alembic needed)."""
    insp = inspect(engine)
    with engine.begin() as conn:
        # users: add last_active
        user_cols = {c["name"] for c in insp.get_columns("users")}
        if "last_active" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_active DATETIME"))
            logger.info("Migration: added users.last_active")

        # conversations: add is_starred
        conv_cols = {c["name"] for c in insp.get_columns("conversations")}
        if "is_starred" not in conv_cols:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN is_starred BOOLEAN DEFAULT 0 NOT NULL"))
            logger.info("Migration: added conversations.is_starred")

        # messages: add feedback, feedback_comment
        msg_cols = {c["name"] for c in insp.get_columns("messages")}
        if "feedback" not in msg_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN feedback BOOLEAN"))
            logger.info("Migration: added messages.feedback")
        if "feedback_comment" not in msg_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN feedback_comment TEXT"))
            logger.info("Migration: added messages.feedback_comment")

        # Drop old feedback table (feedback now lives on messages)
        existing_tables = set(insp.get_table_names())
        if "feedback" in existing_tables:
            conn.execute(text("DROP TABLE feedback"))
            logger.info("Migration: dropped feedback table")


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    _setup_logging(settings.log_level)

    logger.info("Starting InsightXpert (log_level=%s)", settings.log_level)

    # Database
    db = DatabaseConnector()
    db.connect(settings.database_url, auth_token=settings.turso_auth_token)
    logger.info("Database connected: %s", settings.database_url)

    # RAG vector store
    rag = VectorStore(persist_dir=settings.chroma_persist_dir)
    logger.info("ChromaDB initialized: %s", settings.chroma_persist_dir)

    # Bootstrap RAG with InsightXpert training data
    trainer = Trainer(rag)
    try:
        count = trainer.train_insightxpert(db)
        logger.info("RAG bootstrap complete: %d training items loaded", count)
    except Exception as e:
        logger.error("RAG bootstrap failed: %s", e, exc_info=True)

    # LLM provider
    llm = create_llm(settings.llm_provider.value, settings)
    logger.info("LLM provider: %s", settings.llm_provider.value)

    # Auth tables (same database as transactions)
    auth_engine = db.engine
    AuthBase.metadata.create_all(auth_engine)
    _migrate_schema(auth_engine)
    seed_admin(auth_engine)
    logger.info("Auth tables initialized")

    # Persistent conversation store (SQLite-backed)
    persistent_conv_store = PersistentConversationStore(auth_engine)
    logger.info("Persistent conversation store initialized")

    # Conversation memory (in-memory for LLM context)
    conversation_store = ConversationStore()
    logger.info("Conversation memory initialized (in-memory)")

    # Store on app state
    app.state.settings = settings
    app.state.db = db
    app.state.rag = rag
    app.state.llm = llm
    app.state.conversation_store = conversation_store
    app.state.auth_engine = auth_engine
    app.state.persistent_conv_store = persistent_conv_store

    # Admin config (JSON file)
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "client-configs.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        write_config(config_path, read_config(config_path))
        logger.info("Default admin config created: %s", config_path)
    app.state.config_path = config_path
    logger.info("Admin config loaded: %s", config_path)

    logger.info("InsightXpert ready — http://0.0.0.0:8000")
    yield

    db.disconnect()
    logger.info("Shutdown complete")


app = FastAPI(title="InsightXpert", version="0.1.0", lifespan=lifespan)

_settings = Settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(admin_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("insightxpert.main:app", host="0.0.0.0", port=8000, reload=True)
