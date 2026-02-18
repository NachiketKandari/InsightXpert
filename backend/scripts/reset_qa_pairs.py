"""Reset the QA pairs collection in ChromaDB while keeping DDL, docs, and findings.

Usage:
    uv run python scripts/reset_qa_pairs.py                  # uses default ./chroma_data
    uv run python scripts/reset_qa_pairs.py /path/to/chroma  # custom path

After reset, run the server normally — it will re-seed the curated training
QA pairs (with sql_valid=True) on startup via Trainer.train_insightxpert().
"""

from __future__ import annotations

import sys

import chromadb


def reset_qa_pairs(persist_dir: str = "./chroma_data") -> None:
    client = chromadb.PersistentClient(path=persist_dir)

    try:
        qa = client.get_collection("qa_pairs")
        count = qa.count()
    except Exception:
        print(f"No 'qa_pairs' collection found in {persist_dir}. Nothing to do.")
        return

    if count == 0:
        print("qa_pairs collection is already empty.")
        return

    # Show what we're about to delete
    print(f"ChromaDB path: {persist_dir}")
    print(f"qa_pairs count: {count}")

    # Show other collections for reference
    for name in ("ddl", "docs", "findings"):
        try:
            col = client.get_collection(name)
            print(f"{name} count: {col.count()} (keeping)")
        except Exception:
            print(f"{name}: not found")

    print(f"\nDeleting {count} QA pairs...")
    client.delete_collection("qa_pairs")
    client.get_or_create_collection("qa_pairs")
    print("Done. QA pairs cleared. DDL, docs, and findings are untouched.")
    print("Restart the server to re-seed curated training pairs.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "./chroma_data"
    reset_qa_pairs(path)
