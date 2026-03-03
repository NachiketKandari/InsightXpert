#!/usr/bin/env python3
"""One-time migration script: SQLite (insightxpert.db) → PostgreSQL.

Transfers user-data tables in FK-safe order. Skips re-seedable tables
(datasets, dataset_columns, example_queries, prompt_templates, dataset_stats)
and the transactions table (loaded from CSV on startup).

The script can optionally restore the SQLite database from a Litestream
replica on GCS before migrating (requires `litestream` CLI installed).

=== FULL MIGRATION INSTRUCTIONS ===

1. Start PostgreSQL and create the schema:

    cd backend
    docker compose up -d
    uv run python -m insightxpert   # creates tables, loads CSV — then Ctrl+C

2a. If you have the SQLite file locally:

    python scripts/migrate_sqlite_to_pg.py \
      --sqlite insightxpert.db \
      --pg-url postgresql://insightxpert:insightxpert@localhost:5432/insightxpert

2b. If you need to pull the DB from the production Litestream replica on GCS:

    python scripts/migrate_sqlite_to_pg.py \
      --litestream-url gcs://insightxpert-bucket/litestream/insightxpert.db \
      --pg-url postgresql://insightxpert:insightxpert@localhost:5432/insightxpert

    This requires:
      - `litestream` CLI installed (https://litestream.io/install/)
      - GCS credentials configured (gcloud auth application-default login)
    The script will restore the replica to a temp file, migrate, then clean up.

3. Verify: restart the app — it should skip CSV load and use migrated data.

=== WHAT GETS MIGRATED ===

  Migrated (user data):
    organizations, app_settings, users, conversations, messages,
    enrichment_traces, orchestrator_plans, agent_executions,
    automations, automation_runs, automation_triggers, trigger_templates,
    notifications, insights

  Skipped (re-seeded by app on startup):
    datasets, dataset_columns, dataset_stats, example_queries,
    prompt_templates, transactions

  Skipped (SQLite/Litestream internals):
    _litestream_lock, _litestream_seq, _sync_deletes, sqlite_sequence

The script is idempotent — if a PG table already has rows, it is skipped.
"""

import argparse
import os
import subprocess
import sys
import tempfile

import pandas as pd
from sqlalchemy import create_engine, inspect, text

# Tables to migrate in FK-safe order (parents before children).
MIGRATION_ORDER = [
    "organizations",
    "app_settings",
    "users",
    "conversations",
    "messages",
    "enrichment_traces",
    "orchestrator_plans",
    "agent_executions",
    "automations",
    "automation_runs",
    "automation_triggers",
    "trigger_templates",
    "notifications",
    "insights",
]

# Tables the app re-seeds on startup — no need to migrate.
SKIP_TABLES = {
    "datasets",
    "dataset_columns",
    "dataset_stats",
    "example_queries",
    "prompt_templates",
    "transactions",
}

# SQLite internal / Litestream artefacts.
SQLITE_ARTIFACTS = {
    "_litestream_lock",
    "_litestream_seq",
    "_sync_deletes",
    "sqlite_sequence",
}


def restore_from_litestream(replica_url: str) -> str:
    """Restore a SQLite DB from a Litestream replica. Returns path to restored file."""
    fd, tmp = tempfile.mkstemp(suffix=".db", prefix="insightxpert_restore_")
    os.close(fd)
    print(f"Restoring Litestream replica from {replica_url} → {tmp}")
    try:
        subprocess.run(
            ["litestream", "restore", "-o", tmp, replica_url],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("ERROR: `litestream` CLI not found. Install it: https://litestream.io/install/", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: litestream restore failed:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"Restore complete ({os.path.getsize(tmp) / 1024 / 1024:.1f} MB)")
    return tmp


def migrate(sqlite_path: str, pg_url: str) -> None:
    src = create_engine(f"sqlite:///{sqlite_path}")
    dst = create_engine(pg_url)

    src_inspector = inspect(src)
    dst_inspector = inspect(dst)

    src_tables = set(src_inspector.get_table_names())
    dst_tables = set(dst_inspector.get_table_names())

    print(f"Source SQLite tables: {sorted(src_tables)}")
    print(f"Target PostgreSQL tables: {sorted(dst_tables)}")
    print()

    summary: list[tuple[str, int, str]] = []

    for table in MIGRATION_ORDER:
        if table not in src_tables:
            summary.append((table, 0, "not in SQLite"))
            continue

        if table not in dst_tables:
            summary.append((table, 0, "not in PostgreSQL (run app first)"))
            continue

        # Check if PG already has rows — skip if so (safe to re-run).
        with dst.connect() as conn:
            pg_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()  # noqa: S608
            if pg_count and pg_count > 0:
                summary.append((table, 0, f"skipped (PG already has {pg_count} rows)"))
                continue

        df = pd.read_sql_table(table, src)
        if df.empty:
            summary.append((table, 0, "empty in SQLite"))
            continue

        df.to_sql(table, dst, if_exists="append", index=False)
        summary.append((table, len(df), "migrated"))

    # Report any SQLite tables we intentionally skipped.
    skipped_seed = src_tables & SKIP_TABLES
    skipped_artifacts = src_tables & SQLITE_ARTIFACTS
    unknown = src_tables - set(MIGRATION_ORDER) - SKIP_TABLES - SQLITE_ARTIFACTS
    if skipped_seed:
        print(f"Skipped (re-seeded by app): {sorted(skipped_seed)}")
    if skipped_artifacts:
        print(f"Skipped (SQLite artifacts): {sorted(skipped_artifacts)}")
    if unknown:
        print(f"WARNING — unknown tables not migrated: {sorted(unknown)}")
    print()

    # Print summary table.
    print(f"{'Table':<30} {'Rows':>8}  Status")
    print("-" * 60)
    for table, rows, status in summary:
        print(f"{table:<30} {rows:>8}  {status}")

    total = sum(r for _, r, _ in summary)
    print("-" * 60)
    print(f"{'Total':<30} {total:>8}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate InsightXpert user data from SQLite to PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # From a local SQLite file:
  python scripts/migrate_sqlite_to_pg.py \\
    --sqlite insightxpert.db \\
    --pg-url postgresql://insightxpert:insightxpert@localhost:5432/insightxpert

  # Pull from production Litestream replica on GCS:
  python scripts/migrate_sqlite_to_pg.py \\
    --litestream-url gcs://insightxpert-bucket/litestream/insightxpert.db \\
    --pg-url postgresql://insightxpert:insightxpert@localhost:5432/insightxpert
""",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite", help="Path to local SQLite database file")
    source.add_argument("--litestream-url", help="Litestream replica URL (e.g. gcs://bucket/path/db)")
    parser.add_argument("--pg-url", required=True, help="PostgreSQL connection URL")
    args = parser.parse_args()

    sqlite_path = args.sqlite
    tmp_restored = None

    try:
        if args.litestream_url:
            sqlite_path = restore_from_litestream(args.litestream_url)
            tmp_restored = sqlite_path

        migrate(sqlite_path, args.pg_url)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if tmp_restored and os.path.exists(tmp_restored):
            os.unlink(tmp_restored)
            print(f"\nCleaned up temp file: {tmp_restored}")


if __name__ == "__main__":
    main()
