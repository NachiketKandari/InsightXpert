FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application source and transaction data
COPY src/ src/
COPY upi_transactions_2024.csv .

# Pre-download ChromaDB's ONNX embedding model and warm the embedding function
# so it doesn't download/compile at runtime (which can cause startup timeouts)
RUN uv run python -c "\
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; \
ef = DefaultEmbeddingFunction(); \
ef(['warmup']); \
print('ONNX embedding model warmed up')"

ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "insightxpert.main:app", "--host", "0.0.0.0", "--port", "8080"]
