"""Merge-gate requirement per Phase 3 CONTEXT.md — concurrency open-question gate.

Proves that SELECT ... FOR UPDATE plus the idempotency branch results in
exactly ONE audit log row when two clients race to check in the same signup.
Uses real Postgres (not SQLite) with separate DB sessions per thread.

Phase 09: Rewired — Signup now uses volunteer_id (D-01).
"""
import pytest

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import AuditLog, Event, Signup, SignupStatus, Slot, SlotType, User, Volunteer
from app.services.check_in_service import check_in_signup, self_check_in

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/test_uvs",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Create a Postgres engine for concurrency tests."""
    engine = create_engine(TEST_DATABASE_URL, pool_size=5, max_overflow=5)
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def pg_session(pg_engine):
    """Per-test session that rolls back at teardown for isolation."""
    connection = pg_engine.connect()
    trans = connection.begin()
    SessionLocal = sessionmaker(bind=connection, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


def _create_test_data(engine, venue_code="1234"):
    """Create test data in a committed transaction so both threads can see it."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        # Phase 09: Signup keyed to Volunteer, not User (D-01)
        volunteer = Volunteer(
            id=uuid.uuid4(),
            email=f"concurrent-{uuid.uuid4().hex[:8]}@example.com",
            first_name="Concurrent",
            last_name="Vol",
        )
        session.add(volunteer)
        session.flush()

        organizer = User(
            id=uuid.uuid4(),
            name="Organizer",
            email=f"org-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="fakehash",
            role="organizer",
        )
        session.add(organizer)
        session.flush()

        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=organizer.id,
            title="Concurrent Event",
            start_date=now,
            end_date=now + timedelta(days=1),
            venue_code=venue_code,
        )
        session.add(event)
        session.flush()

        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now,
            end_time=now + timedelta(hours=2),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        session.add(slot)
        session.flush()

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=volunteer.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        session.add(signup)
        session.commit()

        return {
            "volunteer_id": volunteer.id,
            "organizer_id": organizer.id,
            "event_id": event.id,
            "slot_id": slot.id,
            "signup_id": signup.id,
        }
    finally:
        session.close()


def _cleanup_test_data(engine, data):
    """Clean up committed test data."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        # Delete in dependency order
        session.execute(
            text("DELETE FROM audit_logs WHERE entity_id = :sid"),
            {"sid": str(data["signup_id"])},
        )
        session.execute(
            text("DELETE FROM signups WHERE id = :sid"),
            {"sid": str(data["signup_id"])},
        )
        session.execute(
            text("DELETE FROM slots WHERE id = :sid"),
            {"sid": str(data["slot_id"])},
        )
        session.execute(
            text("DELETE FROM events WHERE id = :sid"),
            {"sid": str(data["event_id"])},
        )
        # Phase 09: delete volunteer instead of user (D-01)
        session.execute(
            text("DELETE FROM volunteers WHERE id = :v1"),
            {"v1": str(data["volunteer_id"])},
        )
        session.execute(
            text("DELETE FROM users WHERE id = :u2"),
            {"u2": str(data["organizer_id"])},
        )
        session.commit()
    finally:
        session.close()


@pytest.mark.merge_gate
class TestConcurrentCheckIn:
    """Merge-gate: concurrent check-in must produce exactly one audit log."""

    @pytest.mark.parametrize("run", range(5))
    def test_organizer_vs_self_check_in(self, pg_engine, run):
        """Two threads race: organizer check-in vs self check-in.

        Assertions:
        - Both succeed (200 equivalent — no exceptions)
        - Final signup.status == checked_in
        - EXACTLY ONE AuditLog row with action='transition' and to='checked_in'
        - signup.checked_in_at is set exactly once
        """
        data = _create_test_data(pg_engine)
        try:
            barrier = Barrier(2, timeout=10)
            results = [None, None]
            errors = [None, None]

            def thread_organizer():
                """Thread A: organizer check-in."""
                SessionLocal = sessionmaker(bind=pg_engine)
                session = SessionLocal()
                try:
                    barrier.wait()
                    signup = check_in_signup(
                        session, data["signup_id"], data["organizer_id"], via="organizer"
                    )
                    session.commit()
                    results[0] = signup.status.value
                except Exception as e:
                    session.rollback()
                    errors[0] = e
                finally:
                    session.close()

            def thread_self():
                """Thread B: self check-in."""
                SessionLocal = sessionmaker(bind=pg_engine)
                session = SessionLocal()
                try:
                    barrier.wait()
                    signup = self_check_in(
                        session,
                        data["event_id"],
                        data["signup_id"],
                        "1234",
                        data["organizer_id"],
                    )
                    session.commit()
                    results[1] = signup.status.value
                except Exception as e:
                    session.rollback()
                    errors[1] = e
                finally:
                    session.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(thread_organizer)
                f2 = executor.submit(thread_self)
                f1.result(timeout=15)
                f2.result(timeout=15)

            # Both should succeed (no errors)
            assert errors[0] is None, f"Organizer thread error: {errors[0]}"
            assert errors[1] is None, f"Self thread error: {errors[1]}"

            # Both report checked_in
            assert results[0] == "checked_in"
            assert results[1] == "checked_in"

            # Verify in a fresh session
            SessionLocal = sessionmaker(bind=pg_engine)
            verify = SessionLocal()
            try:
                signup = verify.get(Signup, data["signup_id"])
                assert signup.status == SignupStatus.checked_in
                assert signup.checked_in_at is not None

                # EXACTLY ONE audit log for this signup transition
                audit_count = (
                    verify.execute(
                        select(AuditLog).where(
                            AuditLog.entity_id == str(data["signup_id"]),
                            AuditLog.action == "transition",
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(audit_count) == 1, (
                    f"Expected exactly 1 audit log, got {len(audit_count)}"
                )
                assert audit_count[0].extra["to"] == "checked_in"
            finally:
                verify.close()
        finally:
            _cleanup_test_data(pg_engine, data)

    @pytest.mark.parametrize("run", range(5))
    def test_two_organizer_check_ins(self, pg_engine, run):
        """Two organizer threads race to check in the same signup.

        Same assertions as above: exactly one audit log, final status checked_in.
        """
        data = _create_test_data(pg_engine)
        try:
            barrier = Barrier(2, timeout=10)
            results = [None, None]
            errors = [None, None]

            def thread_a():
                SessionLocal = sessionmaker(bind=pg_engine)
                session = SessionLocal()
                try:
                    barrier.wait()
                    signup = check_in_signup(
                        session, data["signup_id"], data["organizer_id"], via="organizer"
                    )
                    session.commit()
                    results[0] = signup.status.value
                except Exception as e:
                    session.rollback()
                    errors[0] = e
                finally:
                    session.close()

            def thread_b():
                SessionLocal = sessionmaker(bind=pg_engine)
                session = SessionLocal()
                try:
                    barrier.wait()
                    signup = check_in_signup(
                        session, data["signup_id"], data["organizer_id"], via="organizer"
                    )
                    session.commit()
                    results[1] = signup.status.value
                except Exception as e:
                    session.rollback()
                    errors[1] = e
                finally:
                    session.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(thread_a)
                f2 = executor.submit(thread_b)
                f1.result(timeout=15)
                f2.result(timeout=15)

            assert errors[0] is None, f"Thread A error: {errors[0]}"
            assert errors[1] is None, f"Thread B error: {errors[1]}"
            assert results[0] == "checked_in"
            assert results[1] == "checked_in"

            SessionLocal = sessionmaker(bind=pg_engine)
            verify = SessionLocal()
            try:
                signup = verify.get(Signup, data["signup_id"])
                assert signup.status == SignupStatus.checked_in
                assert signup.checked_in_at is not None

                audit_rows = (
                    verify.execute(
                        select(AuditLog).where(
                            AuditLog.entity_id == str(data["signup_id"]),
                            AuditLog.action == "transition",
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(audit_rows) == 1, (
                    f"Expected exactly 1 audit log, got {len(audit_rows)}"
                )
            finally:
                verify.close()
        finally:
            _cleanup_test_data(pg_engine, data)
