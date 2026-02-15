from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from insightxpert.auth.models import Base
from insightxpert.config import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Read DB URL from app settings (env vars / .env.local)
settings = Settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# Tables not managed by Alembic (e.g. transactions is created by seed_turso.py)
EXCLUDE_TABLES = {"transactions"}


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
