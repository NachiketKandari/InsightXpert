"""Create isolated ChromaDB instances per model, seeded with training data."""

from __future__ import annotations

import shutil
import tempfile

from insightxpert.db.connector import DatabaseConnector
from insightxpert.rag.store import VectorStore
from insightxpert.training.trainer import Trainer


def create_isolated_rag(db: DatabaseConnector) -> tuple[VectorStore, str]:
    """Create a fresh VectorStore in a temp directory, seeded with training data.

    Returns the store and the temp directory path (caller must clean up).
    """
    temp_dir = tempfile.mkdtemp(prefix="benchmark_rag_")
    rag = VectorStore(persist_dir=temp_dir)
    Trainer(rag).train_insightxpert(db)
    return rag, temp_dir


def reset_qa_pairs(rag: VectorStore) -> None:
    """Flush auto-saved QA pairs and re-seed with curated training pairs only."""
    from insightxpert.training.queries import EXAMPLE_QUERIES

    rag.flush_qa_pairs()
    for qa in EXAMPLE_QUERIES:
        rag.add_qa_pair(qa["question"], qa["sql"], {"source": "insightxpert_training", "sql_valid": True})


def cleanup_rag(temp_dir: str) -> None:
    """Remove a temporary RAG directory."""
    shutil.rmtree(temp_dir, ignore_errors=True)
