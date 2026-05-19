# backend/alembic/env.py
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import settings
from app.database import Base
from app import models  # ensures models are imported

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers defaults to True, which sets
    # `disabled=True` on every logger created before this call. In tests
    # the corpus suite invokes `alembic upgrade head` mid-session, and
    # that silently kills `app.emails` / `app.celery_app` / all other
    # already-imported loggers — caplog and direct handlers alike see
    # nothing for the rest of the run.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": settings.database_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Revision IDs in this project use descriptive slugs (up to ~60 chars)
        # that overflow alembic's default VARCHAR(32) version_num column. Ensure
        # the column is wide enough before running migrations. Safe to run on
        # every startup — no-op if already widened or table not yet created.
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(128) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        ))
        connection.execute(text(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(128)"
        ))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
