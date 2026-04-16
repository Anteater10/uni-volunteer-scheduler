"""Verify PublicSlotRead serializes time fields as naive ISO (no Z suffix).

Bug: SlotRead emitted "2026-04-16T09:00:00Z" — the Z lied about UTC.
Frontend then converted UTC → local, dropping 7 hours in PDT.

Fix: serializer emits "2026-04-16T09:00:00" — browsers parse as local
wall-clock time, no offset shift.
"""
from datetime import date, datetime, timezone
from uuid import uuid4

from app.schemas import PublicSlotRead
from app.models import SlotType


def test_public_slot_read_serializes_times_without_z():
    # Simulate what the ORM returns: timezone-aware datetimes (UTC-marked).
    # The bug was that model_dump(mode="json") emitted "...Z" for these,
    # which made browsers subtract the local UTC offset (−7 h in PDT).
    slot = PublicSlotRead(
        id=uuid4(),
        slot_type=SlotType.ORIENTATION,
        date=date(2026, 4, 16),
        start_time=datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc),
        location="E2E Hall Room A",
        capacity=200,
        filled=12,
        signups=[],
    )
    payload = slot.model_dump(mode="json")
    assert payload["start_time"] == "2026-04-16T09:00:00"
    assert payload["end_time"] == "2026-04-16T10:00:00"
    assert "Z" not in payload["start_time"]
    assert "Z" not in payload["end_time"]


def test_public_slot_read_serializes_naive_times_unchanged():
    # Exercise the "already correct" branch of _serialize_naive:
    # when input is already naive (no tzinfo), it should serialize as-is.
    slot = PublicSlotRead(
        id=uuid4(),
        slot_type=SlotType.ORIENTATION,
        date=date(2026, 4, 16),
        start_time=datetime(2026, 4, 16, 9, 0),
        end_time=datetime(2026, 4, 16, 10, 0),
        location="E2E Hall Room A",
        capacity=200,
        filled=12,
        signups=[],
    )
    payload = slot.model_dump(mode="json")
    assert payload["start_time"] == "2026-04-16T09:00:00"
    assert payload["end_time"] == "2026-04-16T10:00:00"
    assert "Z" not in payload["start_time"]
    assert "Z" not in payload["end_time"]
