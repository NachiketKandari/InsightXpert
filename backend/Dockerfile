FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application source and Alembic migrations
COPY src/ src/
COPY alembic.ini alembic.ini
COPY alembic/ alembic/

# Load real CSV data into SQLite and clean up
COPY generate_data.py upi_transactions_2024.csv ./
RUN uv run python generate_data.py && rm generate_data.py upi_transactions_2024.csv

# Pre-download ChromaDB's ONNX embedding model so it doesn't download at runtime
RUN uv run python -c "import chromadb; chromadb.Client()"

ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "insightxpert.main:app", "--host", "0.0.0.0", "--port", "8080"]
