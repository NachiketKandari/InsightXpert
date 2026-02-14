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

# Generate the 250K-row transactions database
COPY generate_data.py .
RUN uv run python generate_data.py && rm generate_data.py

# ChromaDB / RAG data is bootstrapped at runtime by the app lifespan

ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "insightxpert.main:app", "--host", "0.0.0.0", "--port", "8080"]
