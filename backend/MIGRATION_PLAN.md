# Migration Plan: SQLite → Cloud SQL PostgreSQL

## Progress Tracker

- [x] Phase 2: Dependencies & Config
  - [x] `pyproject.toml` — psycopg2-binary → main deps
  - [x] `config.py` — Default DATABASE_URL, add CLOUD_SQL_CONNECTION_NAME
  - [ ] `docker-compose.yml` — New local PostgreSQL service
- [x] Phase 3: Database Connector
  - [x] `db/connector.py` — Remove SQLite PRAGMAs, add PG pool config
- [x] Phase 4: Schema & Models
  - [x] `db/migrations.py` — BOOLEAN DEFAULT 0 → DEFAULT FALSE
  - [x] `training/schema.py` — DDL types to PostgreSQL
- [x] Phase 5: Stats Computer
  - [x] `db/stats_computer.py` — STRFTIME → TO_CHAR, DATE() → ::date
- [x] Phase 6: Dataset Service & Profiler
  - [x] `datasets/profiler.py` — REAL → DOUBLE PRECISION, DATETIME → TIMESTAMP, reserved words
  - [x] `datasets/service.py` — Docstring updates
- [x] Phase 7: LLM Prompts & Training Data
  - [x] `prompts/analyst_system.j2` — "SQLite" → "PostgreSQL"
  - [x] `training/schema.py` — PostgreSQL DDL types
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
