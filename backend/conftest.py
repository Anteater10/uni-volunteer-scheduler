import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/test_uvs",
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db_session(engine):
    """Transactional test session.

    Uses the standard SQLAlchemy "join external transaction" pattern:
    - open an outer transaction on a connection
    - bind a Session to that connection in nested/savepoint mode
    - restart the SAVEPOINT after any inner `session.commit()` so router
      code that calls `db.commit()` does not escape the rollback
    - rollback the outer transaction at teardown

    This lets tests exercise real router code (which commits) without
    persisting data between tests.
    """
    connection = engine.connect()
    trans = connection.begin()
    Session = sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    session = Session()

    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
