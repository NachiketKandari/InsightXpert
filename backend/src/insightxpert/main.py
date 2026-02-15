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
from insightxpert.auth.routes import router as auth_router
from insightxpert.auth.seed import seed_admin, seed_default_user
from insightxpert.config import Settings
from insightxpert.llm.factory import create_llm
from insightxpert.db.connector import DatabaseConnector
from insightxpert.memory.conversation_store import ConversationStore
from insightxpert.rag.store import VectorStore
from insightxpert.training.trainer import Trainer

logger = logging.getLogger("insightxpert")


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

    # Auth tables — run Alembic migrations
    auth_engine = db.engine
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    alembic_cfg = AlembicConfig(str(Path(__file__).resolve().parent.parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", str(auth_engine.url))
    alembic_command.upgrade(alembic_cfg, "head")

    seed_admin(auth_engine)
    seed_default_user(auth_engine)
    logger.info("Auth tables initialized (via Alembic)")

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
