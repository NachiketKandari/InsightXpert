from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import create_engine

from insightxpert.api.routes import router
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.models import Base as AuthBase
from insightxpert.auth.routes import router as auth_router
from insightxpert.auth.seed import seed_admin
from insightxpert.config import LLMProvider, Settings
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
    db.connect(settings.database_url)
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
    if settings.llm_provider == LLMProvider.GEMINI:
        from insightxpert.llm.gemini import GeminiProvider
        llm = GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
        logger.info("LLM provider: Gemini (%s)", settings.gemini_model)
    else:
        from insightxpert.llm.ollama import OllamaProvider
        llm = OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url)
        logger.info("LLM provider: Ollama (%s @ %s)", settings.ollama_model, settings.ollama_base_url)

    # Auth database (separate SQLite file)
    auth_engine = create_engine("sqlite:///./insightxpert_auth.db")
    AuthBase.metadata.create_all(auth_engine)
    seed_admin(auth_engine)
    logger.info("Auth database initialized")

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

    logger.info("InsightXpert ready — http://0.0.0.0:8000")
    yield

    db.disconnect()
    logger.info("Shutdown complete")


app = FastAPI(title="InsightXpert", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("insightxpert.main:app", host="0.0.0.0", port=8000, reload=True)
