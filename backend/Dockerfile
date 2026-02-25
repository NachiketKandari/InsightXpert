FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ src/

# Pre-download ChromaDB's ONNX embedding model so it doesn't download at runtime
RUN uv run python -c "import chromadb; chromadb.Client()"

ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "insightxpert.main:app", "--host", "0.0.0.0", "--port", "8080"]
