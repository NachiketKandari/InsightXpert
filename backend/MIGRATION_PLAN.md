# Migration Plan: SQLite → Cloud SQL PostgreSQL

## Progress Tracker

- [ ] Phase 2: Dependencies & Config
  - [ ] `pyproject.toml` — psycopg2-binary → main deps
  - [ ] `config.py` — Default DATABASE_URL, add CLOUD_SQL_CONNECTION_NAME
  - [ ] `docker-compose.yml` — New local PostgreSQL service
- [ ] Phase 3: Database Connector
  - [ ] `db/connector.py` — Remove SQLite PRAGMAs, add PG pool config
- [ ] Phase 4: Schema & Models
  - [ ] `db/migrations.py` — BOOLEAN DEFAULT 0 → DEFAULT FALSE
  - [ ] `training/schema.py` — DDL types to PostgreSQL
- [ ] Phase 5: Stats Computer
  - [ ] `db/stats_computer.py` — STRFTIME → TO_CHAR, DATE() → ::date
- [ ] Phase 6: Dataset Service & Profiler
  - [ ] `datasets/profiler.py` — REAL → DOUBLE PRECISION, DATETIME → TIMESTAMP, reserved words
  - [ ] `datasets/service.py` — Docstring updates
- [ ] Phase 7: LLM Prompts & Training Data
  - [ ] `prompts/analyst_system.j2` — "SQLite" → "PostgreSQL"
  - [ ] `training/schema.py` — PostgreSQL DDL types
- [ ] Phase 8: Data Loading
  - [ ] `generate_data.py` — sqlite3 → SQLAlchemy
- [ ] Phase 9: Startup
  - [ ] `main.py` — Remove pg_overrides, update comments
- [ ] Phase 10: Docker & Deployment
  - [ ] `Dockerfile` — Remove Litestream
  - [ ] `entrypoint.sh` — Remove Litestream logic
  - [ ] `litestream.yml` — Delete
  - [ ] `deploy.yml` — Cloud SQL connection, env vars
  - [ ] `preview.yml` — PostgreSQL test DB
- [ ] Phase 11: Cleanup
  - [ ] `CLAUDE.md` — Update references
