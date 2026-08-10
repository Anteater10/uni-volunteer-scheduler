# backend/app/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

# Every argument here was previously a default, and the defaults are wrong
# for a deployed service:
#
# * ``pool_pre_ping`` — Postgres or the network drops idle connections. A
#   pooled-but-dead connection surfaces as a 500 on the next request that
#   happens to draw it, at a moment unrelated to the actual failure.
# * ``pool_recycle`` — bounds how long a connection can sit before it is
#   retired, so we do not accumulate connections older than the proxy's or
#   the database's own idle timeout.
# * ``pool_timeout`` — without it, a request that finds the pool exhausted
#   waits 30s (the default) holding a worker, which turns a slow query into
#   a full outage. Ten seconds fails fast enough to shed load.
# * ``connect_timeout`` — a database that is up but unreachable would
#   otherwise block indefinitely at connect.
# * ``statement_timeout`` — the ceiling that keeps one pathological query
#   from pinning a connection for the rest of the day. Celery overrides this
#   for its own longer jobs.
#
# Sizing: (pool_size + max_overflow) × workers + Celery must stay under the
# server's max_connections. At the defaults below and 4 workers that is 40,
# comfortably under Postgres' default 100.
engine = create_engine(
    settings.database_url,
    future=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=10,
    connect_args={
        "connect_timeout": 5,
        "application_name": "uvs-api",
        "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
    },
)

# Force UTC at the DB connection/session level
@event.listens_for(engine, "connect")
def _set_sql_timezone(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET TIME ZONE 'UTC';")
    cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
