"""Migration 0044: the slot-lock backfill and its one-way data repair.

Seeded with the shapes Kim's real data had on 2026-10-13:

- a past orientation where everyone was resolved -> closed;
- a past orientation with one person still unconfirmed -> stays open, and its
  attended / no_show are repaired back to checked in / not checked in;
- a future orientation everyone was (wrongly) resolved on -> open + repaired,
  because a slot that has not started is never closed;
- a past session where everybody was a no-show -> closed;
- a two-day shift ended early by the old "End event": Tuesday has a seated
  commitment with no record -> open + repaired; Thursday is in the future and
  every seat holds a no-show -> open, and the no-shows are deleted.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

_PRE = "0043_add_event_display_week"


def _id():
    return str(uuid.uuid4())


def _seed(conn):
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=2)
    future = now + timedelta(days=2)
    ids = {"owner": _id(), "event": _id()}

    conn.execute(
        text(
            "INSERT INTO users (id, name, email, role, notify_email, created_at) "
            "VALUES (:id, 'Owner', :email, 'organizer', true, now())"
        ),
        {"id": ids["owner"], "email": f"{ids['owner']}@mig.test"},
    )
    conn.execute(
        text(
            "INSERT INTO events (id, owner_id, title, start_date, end_date) "
            "VALUES (:id, :owner, 'Kim week', :start, :end)"
        ),
        {"id": ids["event"], "owner": ids["owner"], "start": past, "end": future},
    )

    def slot(key, start, *, shift=None):
        ids[key] = _id()
        conn.execute(
            text(
                "INSERT INTO slots (id, event_id, start_time, end_time, capacity, "
                "current_count, slot_type, date, shift_id, sort_order) VALUES "
                "(:id, :eid, :start, :end, 10, 0, :stype, :date, :shift, 0)"
            ),
            {
                "id": ids[key], "eid": ids["event"], "start": start,
                "end": start + timedelta(hours=1),
                "stype": "period" if shift else "orientation",
                "date": start.date(), "shift": ids[shift] if shift else None,
            },
        )

    def volunteer():
        vid = _id()
        conn.execute(
            text(
                "INSERT INTO volunteers (id, email, first_name, last_name) "
                "VALUES (:id, :email, 'V', 'W')"
            ),
            {"id": vid, "email": f"{vid}@mig.test"},
        )
        return vid

    def signup(key, slot_key, status, checked_in_at=None):
        ids[key] = _id()
        conn.execute(
            text(
                "INSERT INTO signups (id, volunteer_id, slot_id, status, timestamp, "
                "checked_in_at) VALUES (:id, :vid, :slot, :status, now(), :ci)"
            ),
            {
                "id": ids[key], "vid": volunteer(), "slot": ids[slot_key],
                "status": status, "ci": checked_in_at,
            },
        )

    def shift(key):
        ids[key] = _id()
        conn.execute(
            text(
                "INSERT INTO shifts (id, event_id, name, sort_order, capacity, "
                "current_count) VALUES (:id, :eid, :name, 0, 10, 0)"
            ),
            {"id": ids[key], "eid": ids["event"], "name": key},
        )

    def commitment(key, shift_key, status="confirmed"):
        ids[key] = _id()
        conn.execute(
            text(
                "INSERT INTO shift_signups (id, shift_id, volunteer_id, status, "
                "timestamp) VALUES (:id, :shift, :vid, :status, now())"
            ),
            {"id": ids[key], "shift": ids[shift_key], "vid": volunteer(), "status": status},
        )

    def attendance(commit_key, slot_key, status, checked_in_at=None):
        conn.execute(
            text(
                "INSERT INTO session_attendance (id, shift_signup_id, slot_id, "
                "status, checked_in_at) VALUES (:id, :c, :s, :status, :ci)"
            ),
            {
                "id": _id(), "c": ids[commit_key], "s": ids[slot_key],
                "status": status, "ci": checked_in_at,
            },
        )

    ids["checked_at"] = past + timedelta(minutes=5)

    # Orientation 6 Oct: past, fully resolved -> closed.
    slot("o_done", past - timedelta(days=1))
    signup("o_done_att", "o_done", "attended", ids["checked_at"])
    signup("o_done_ns", "o_done", "no_show")
    signup("o_done_cxl", "o_done", "cancelled")

    # Orientation 9 Oct: past, Parker still pending -> open + repaired.
    slot("o_open", past)
    signup("o_open_att", "o_open", "attended", ids["checked_at"])
    signup("o_open_walkin", "o_open", "attended")
    signup("o_open_ns", "o_open", "no_show", ids["checked_at"])
    signup("o_open_parker", "o_open", "pending")

    # A future orientation somebody resolved anyway -> open + repaired.
    slot("o_future", future)
    signup("o_future_ns", "o_future", "no_show")

    # A past orientation with only waitlisted / cancelled -> nothing to close.
    slot("o_empty", past)
    signup("o_empty_wl", "o_empty", "waitlisted")

    # Tue Shift 2: past, every seat a no-show -> closed.
    shift("shift2")
    slot("tue2", past, shift="shift2")
    commitment("s2_a", "shift2")
    commitment("s2_b", "shift2")
    commitment("s2_wl", "shift2", "waitlisted")
    attendance("s2_a", "tue2", "no_show")
    attendance("s2_b", "tue2", "no_show")

    # Shift 1: Tue past (one seat unrecorded), Thu future (all no-show).
    shift("shift1")
    slot("tue1", past, shift="shift1")
    slot("thu1", future, shift="shift1")
    commitment("s1_here", "shift1")
    commitment("s1_gone", "shift1")
    commitment("s1_new", "shift1", "pending")
    attendance("s1_here", "tue1", "attended", ids["checked_at"])
    attendance("s1_gone", "tue1", "no_show")
    attendance("s1_here", "thu1", "no_show")
    attendance("s1_gone", "thu1", "no_show")
    attendance("s1_new", "thu1", "no_show")

    # Shift 3: past session where only a cancelled commitment has a row ->
    # no seated booking resolved, so it stays open (and the row is repaired).
    shift("shift3")
    slot("tue3", past, shift="shift3")
    commitment("s3_cxl", "shift3", "cancelled")
    attendance("s3_cxl", "tue3", "attended", ids["checked_at"])

    # A walk-in recorded attended on the open Tue session with no check-in
    # time: repaired to checked in, stamped at migration time.
    commitment("s1_walk", "shift1")
    attendance("s1_walk", "tue1", "attended")

    # The old "End event" had stamped Kim's week completed.
    conn.execute(
        text("UPDATE events SET completed_at = :t WHERE id = :id"),
        {"t": past, "id": ids["event"]},
    )

    def event(key, completed_at=None):
        ids[key] = _id()
        conn.execute(
            text(
                "INSERT INTO events (id, owner_id, title, start_date, end_date, "
                "completed_at) VALUES (:id, :owner, :title, :start, :end, :done)"
            ),
            {
                "id": ids[key], "owner": ids["owner"], "title": key,
                "start": past, "end": past, "done": completed_at,
            },
        )
        ids["event"] = ids[key]  # slot() books onto ids["event"]

    ids["event_saved"] = ids["event"]
    # Fully resolved but never stamped -> stamped.
    event("ev_done")
    slot("ev_done_slot", past)
    signup("ev_done_a", "ev_done_slot", "attended", ids["checked_at"])
    # Stamped, all closed -> stamp kept as it was.
    ids["kept_at"] = past - timedelta(hours=3)
    event("ev_kept", ids["kept_at"])
    slot("ev_kept_slot", past)
    signup("ev_kept_ns", "ev_kept_slot", "no_show")
    # Stamped, but nobody seated anywhere -> cleared.
    event("ev_empty", past)
    slot("ev_empty_slot", past)
    signup("ev_empty_cxl", "ev_empty_slot", "cancelled")
    ids["event"] = ids["event_saved"]

    # Credits. Only an auto-grant whose grant audit row names a signup that
    # still exists gets linked.
    def credit(key, source, audit_signup=None):
        ids[key] = _id()
        conn.execute(
            text(
                "INSERT INTO orientation_credits (id, volunteer_email, family_key, "
                "source, created_at) VALUES (:id, 'x@mig.test', 'fam', :src, now())"
            ),
            {"id": ids[key], "src": source},
        )
        if audit_signup is not None:
            conn.execute(
                text(
                    "INSERT INTO audit_logs (id, action, entity_type, entity_id, "
                    "extra, timestamp) VALUES (:id, 'orientation_credit_grant', "
                    "'OrientationCredit', :cid, CAST(:extra AS json), now())"
                ),
                {
                    "id": _id(), "cid": ids[key],
                    "extra": '{"signup_id": "%s", "via": "resolve_slot"}' % audit_signup,
                },
            )

    credit("cr_linked", "attendance", ids["o_open_att"])
    credit("cr_gone", "attendance", _id())
    credit("cr_hand", "grant", ids["o_done_att"])
    credit("cr_no_audit", "attendance")
    return ids


def _closed(conn, slot_id):
    return conn.execute(
        text("SELECT closed_at IS NOT NULL FROM slots WHERE id = :id"), {"id": slot_id}
    ).scalar_one()


def _signup(conn, sid):
    return conn.execute(
        text("SELECT status::text, checked_in_at FROM signups WHERE id = :id"),
        {"id": sid},
    ).one()


def _rows(conn, slot_id):
    return {
        str(r.shift_signup_id): (r.status, r.checked_in_at)
        for r in conn.execute(
            text(
                "SELECT shift_signup_id, status::text AS status, checked_in_at "
                "FROM session_attendance WHERE slot_id = :id"
            ),
            {"id": slot_id},
        )
    }


def test_0044_closes_finished_slots_and_repairs_the_rest(alembic_engine, alembic_command):
    alembic_command.downgrade(_PRE)
    with alembic_engine.begin() as conn:
        ids = _seed(conn)
    alembic_command.upgrade("head")

    at = ids["checked_at"]
    with alembic_engine.connect() as conn:
        closed = {k: _closed(conn, ids[k]) for k in (
            "o_done", "o_open", "o_future", "o_empty", "tue2", "tue1", "thu1", "tue3",
        )}
        assert closed == {
            "o_done": True, "o_open": False, "o_future": False, "o_empty": False,
            "tue2": True, "tue1": False, "thu1": False, "tue3": False,
        }

        # Closed slots keep their results untouched.
        assert _signup(conn, ids["o_done_att"]) == ("attended", at)
        assert _signup(conn, ids["o_done_ns"]) == ("no_show", None)
        assert set(_rows(conn, ids["tue2"]).values()) == {("no_show", None)}

        # Open orientation: attended -> checked in (time kept), no_show ->
        # not checked in (time cleared), pending untouched.
        assert _signup(conn, ids["o_open_att"]) == ("checked_in", at)
        walk = _signup(conn, ids["o_open_walkin"])
        # Never had a check-in time: stamped now, so checked in always has one.
        assert walk[0] == "checked_in" and walk[1] is not None
        assert _signup(conn, ids["o_open_ns"]) == ("confirmed", None)
        assert _signup(conn, ids["o_open_parker"]) == ("pending", None)
        assert _signup(conn, ids["o_future_ns"]) == ("confirmed", None)
        assert _signup(conn, ids["o_empty_wl"]) == ("waitlisted", None)

        # Open sessions: attended -> checked in, no_show rows deleted.
        tue1 = _rows(conn, ids["tue1"])
        walk_status, walk_at = tue1.pop(ids["s1_walk"])
        assert walk_status == "checked_in" and walk_at is not None
        assert tue1 == {ids["s1_here"]: ("checked_in", at)}
        assert _rows(conn, ids["thu1"]) == {}
        assert _rows(conn, ids["tue3"]) == {ids["s3_cxl"]: ("checked_in", at)}

        audits = conn.execute(
            text(
                "SELECT entity_type, entity_id, actor_id, action, "
                "extra->>'from' AS from_s, extra->>'to' AS to_s, extra->>'slot_id' AS slot, "
                "extra->>'shift_id' AS shift, timestamp "
                "FROM audit_logs WHERE extra->>'via' = 'migration_0044'"
            )
        ).all()
        got = {(a.entity_type, a.entity_id, a.from_s, a.to_s, a.slot) for a in audits}
        assert got == {
            ("signup", ids["o_open_att"], "attended", "checked_in", None),
            ("signup", ids["o_open_walkin"], "attended", "checked_in", None),
            ("signup", ids["o_open_ns"], "no_show", "confirmed", None),
            ("signup", ids["o_future_ns"], "no_show", "confirmed", None),
            ("session_attendance", ids["s1_here"], "attended", "checked_in", ids["tue1"]),
            ("session_attendance", ids["s1_walk"], "attended", "checked_in", ids["tue1"]),
            ("session_attendance", ids["s1_gone"], "no_show", None, ids["tue1"]),
            ("session_attendance", ids["s1_here"], "no_show", None, ids["thu1"]),
            ("session_attendance", ids["s1_gone"], "no_show", None, ids["thu1"]),
            ("session_attendance", ids["s1_new"], "no_show", None, ids["thu1"]),
            ("session_attendance", ids["s3_cxl"], "attended", "checked_in", ids["tue3"]),
        }
        assert len(audits) == len(got)
        assert all(a.action == "transition" and a.actor_id is None for a in audits)
        assert all(a.timestamp is not None for a in audits)
        assert {a.shift for a in audits if a.entity_type == "session_attendance"} == {
            ids["shift1"], ids["shift3"],
        }

        # Step 3: credit links.
        links = dict(
            conn.execute(
                text("SELECT id::text, source_signup_id::text FROM orientation_credits")
            ).all()
        )
        assert links == {
            ids["cr_linked"]: ids["o_open_att"],
            ids["cr_gone"]: None,
            ids["cr_hand"]: None,
            ids["cr_no_audit"]: None,
        }

        # Step 4: completed_at follows the closed switches.
        done = dict(
            conn.execute(text("SELECT id::text, completed_at FROM events")).all()
        )
        assert done[ids["event"]] is None  # Thursday etc. reopened
        assert done[ids["ev_done"]] is not None
        assert done[ids["ev_kept"]] == ids["kept_at"]
        assert done[ids["ev_empty"]] is None

        # New columns exist.
        cols = {
            (r.table_name, r.column_name)
            for r in conn.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE column_name IN ('closed_at', 'closed_by', 'source_signup_id')"
                )
            )
        }
        assert {("slots", "closed_at"), ("slots", "closed_by"),
                ("orientation_credits", "source_signup_id")} <= cols


def test_0044_downgrade_drops_the_columns_and_round_trips(alembic_engine, alembic_command):
    alembic_command.downgrade(_PRE)
    with alembic_engine.begin() as conn:
        ids = _seed(conn)
    alembic_command.upgrade("head")
    alembic_command.downgrade(_PRE)

    with alembic_engine.connect() as conn:
        cols = {
            (r.table_name, r.column_name)
            for r in conn.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE column_name IN ('closed_at', 'closed_by', 'source_signup_id')"
                )
            )
        }
        assert ("slots", "closed_at") not in cols
        assert ("orientation_credits", "source_signup_id") not in cols
        # One-way repair: the downgrade leaves the repaired statuses alone.
        assert _signup(conn, ids["o_open_ns"])[0] == "confirmed"

    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        # Re-running the backfill is stable: the same slots close, nothing
        # else is repaired twice.
        assert _closed(conn, ids["o_done"]) and _closed(conn, ids["tue2"])
        assert not _closed(conn, ids["o_open"])
        assert conn.execute(
            text("SELECT count(*) FROM audit_logs WHERE extra->>'via' = 'migration_0044'")
        ).scalar() == 11
