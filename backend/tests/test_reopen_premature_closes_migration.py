"""Migration 0045: reopen sessions that 0044 closed on results written before
they started.

Kim's week (2026-10-13/15): the old "End event" on Tuesday wrote ``no_show``
for every confirmed student on Tuesday's *and* Thursday's sessions. If 0044
runs after Thursday's sessions have started, it sees "started, everyone
resolved" and closes Thursday, keeping the bogus no-shows. 0045 finds results
written before their session started and reopens those sessions.

The tests run the real chain: seed at 0043, upgrade to 0044 (which closes the
Thursday sessions), then upgrade to 0045.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

_PRE_0044 = "0043_add_event_display_week"
_PRE = "0044_slot_closed_at_and_credit_source"
_REV = "0045_reopen_premature_closes"


def _id():
    return str(uuid.uuid4())


def _seed(conn):
    now = datetime.now(timezone.utc)
    tue = now - timedelta(days=2)
    thu = now - timedelta(hours=1)  # Thursday's sessions have started
    tue_end_event = tue + timedelta(hours=2)  # the old "End event" tap
    ids = {"owner": _id(), "tue": tue, "thu": thu, "now": now}

    conn.execute(
        text(
            "INSERT INTO users (id, name, email, role, notify_email, created_at) "
            "VALUES (:id, 'Owner', :email, 'organizer', true, now())"
        ),
        {"id": ids["owner"], "email": f"{ids['owner']}@mig.test"},
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
                "start": tue, "end": thu, "done": completed_at,
            },
        )
        ids["event"] = ids[key]

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

    def attendance(commit_key, slot_key, status, written_at, checked_in_at=None):
        conn.execute(
            text(
                "INSERT INTO session_attendance (id, shift_signup_id, slot_id, "
                "status, checked_in_at, created_at, updated_at) "
                "VALUES (:id, :c, :s, :status, :ci, :at, :at)"
            ),
            {
                "id": _id(), "c": ids[commit_key], "s": ids[slot_key],
                "status": status, "ci": checked_in_at, "at": written_at,
            },
        )

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

    def transition_audit(signup_key, frm, to, at):
        conn.execute(
            text(
                "INSERT INTO audit_logs (id, action, entity_type, entity_id, extra, "
                "timestamp) VALUES (:id, 'transition', 'signup', :sid, "
                "CAST(:extra AS json), :at)"
            ),
            {
                "id": _id(), "sid": ids[signup_key], "at": at,
                "extra": '{"from": "%s", "to": "%s", "via": "resolve_event"}' % (frm, to),
            },
        )

    ids["tue_checked_at"] = tue + timedelta(minutes=5)
    ids["thu_checked_at"] = thu - timedelta(minutes=10)

    # ---- Kim's week: stamped completed by the old "End event". ----
    event("kim", completed_at=tue_end_event)

    # Shift 2: Tue resolved after it started (genuine); Thu every confirmed
    # student got a no-show on Tuesday (bogus). 0044 closes both.
    shift("shift2")
    slot("tue2", tue, shift="shift2")
    slot("thu2", thu, shift="shift2")
    commitment("s2_a", "shift2")
    commitment("s2_b", "shift2")
    attendance("s2_a", "tue2", "attended", tue_end_event, ids["tue_checked_at"])
    attendance("s2_b", "tue2", "no_show", tue_end_event)
    attendance("s2_a", "thu2", "no_show", tue_end_event)
    attendance("s2_b", "thu2", "no_show", tue_end_event)

    # Shift 4: Thu holds a mix. One student was marked attended before the
    # session started (kept check-in time), one attended with no time, and one
    # no-show was written after the start. Every final row on a reopened
    # session goes back to "not resolved", because attended / no_show only
    # exist on a closed slot.
    shift("shift4")
    slot("thu4", thu, shift="shift4")
    commitment("s4_early", "shift4")
    commitment("s4_walk", "shift4")
    commitment("s4_late_ns", "shift4")
    attendance("s4_early", "thu4", "attended", thu - timedelta(minutes=5),
               ids["thu_checked_at"])
    attendance("s4_walk", "thu4", "attended", thu - timedelta(minutes=5))
    attendance("s4_late_ns", "thu4", "no_show", thu + timedelta(minutes=20))

    # Orientation resolved on Tuesday, before it started on Thursday: the
    # audit trail proves it -> reopened and repaired.
    slot("o_bogus", thu)
    signup("o_bogus_att", "o_bogus", "attended", ids["thu_checked_at"])
    signup("o_bogus_ns", "o_bogus", "no_show")
    transition_audit("o_bogus_att", "checked_in", "attended", tue_end_event)
    transition_audit("o_bogus_ns", "confirmed", "no_show", tue_end_event)

    # ---- A genuinely finished week: results written after each start. ----
    ids["done_at"] = tue_end_event
    event("genuine", completed_at=ids["done_at"])
    shift("shift5")
    slot("thu5", thu, shift="shift5")
    commitment("s5_a", "shift5")
    commitment("s5_b", "shift5")
    attendance("s5_a", "thu5", "attended", thu + timedelta(minutes=30),
               ids["thu_checked_at"])
    attendance("s5_b", "thu5", "no_show", thu + timedelta(minutes=30))

    # Closed the moment it started (start + 0), and once with the app clock a
    # fraction of a second behind the database: both are genuine closes. The
    # "written before start" test allows one second of tolerance.
    shift("shift6")
    slot("thu6", thu, shift="shift6")
    commitment("s6_a", "shift6")
    commitment("s6_b", "shift6")
    attendance("s6_a", "thu6", "no_show", thu)
    attendance("s6_b", "thu6", "attended", thu - timedelta(milliseconds=500),
               ids["thu_checked_at"])
    slot("o_at_start", thu)
    signup("o_at_start_ns", "o_at_start", "no_show")
    transition_audit("o_at_start_ns", "confirmed", "no_show",
                     thu - timedelta(milliseconds=500))

    # Orientation resolved after it started -> stays closed.
    slot("o_genuine", thu)
    signup("o_genuine_att", "o_genuine", "attended", ids["thu_checked_at"])
    transition_audit("o_genuine_att", "checked_in", "attended", thu + timedelta(minutes=30))

    # Orientation resolved with no audit trail at all: the time it was written
    # is unknown, so it is left alone.
    slot("o_no_audit", thu)
    signup("o_no_audit_ns", "o_no_audit", "no_show")

    # Orientation whose last audited transition does not match the status it
    # holds now: the trail is incomplete, so it is left alone too.
    slot("o_mismatch", thu)
    signup("o_mismatch_ns", "o_mismatch", "no_show")
    transition_audit("o_mismatch_ns", "confirmed", "checked_in", tue_end_event)
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


_SLOTS = ("tue2", "thu2", "thu4", "o_bogus", "thu5", "o_genuine", "o_no_audit",
          "o_mismatch", "thu6", "o_at_start")


def _run_to_0044(alembic_engine, alembic_command):
    alembic_command.downgrade(_PRE_0044)
    with alembic_engine.begin() as conn:
        ids = _seed(conn)
    alembic_command.upgrade(_PRE)
    with alembic_engine.connect() as conn:
        # The bug: 0044 run after Thursday started closes Thursday too.
        assert all(_closed(conn, ids[k]) for k in _SLOTS)
    return ids


def test_0045_reopens_sessions_closed_on_results_written_before_they_started(
    alembic_engine, alembic_command
):
    ids = _run_to_0044(alembic_engine, alembic_command)
    # An unrelated event whose completion stamp has drifted from its slots
    # (all closed, but not stamped). 0045 only recomputes events it reopened
    # a slot on, so this one is left as it is.
    with alembic_engine.begin() as conn:
        conn.execute(
            text("UPDATE events SET completed_at = NULL WHERE id = :id"),
            {"id": ids["genuine"]},
        )
    alembic_command.upgrade(_REV)

    with alembic_engine.connect() as conn:
        closed = {k: _closed(conn, ids[k]) for k in _SLOTS}
        assert closed == {
            "tue2": True, "thu2": False, "thu4": False, "o_bogus": False,
            "thu5": True, "o_genuine": True, "o_no_audit": True, "o_mismatch": True,
            "thu6": True, "o_at_start": True,
        }
        closed_by = conn.execute(
            text("SELECT count(*) FROM slots WHERE closed_at IS NULL "
                 "AND closed_by IS NOT NULL")
        ).scalar()
        assert closed_by == 0

        # Kim's Thursday Shift 2 is open and clean: nobody is a no-show.
        assert _rows(conn, ids["thu2"]) == {}
        # Tuesday was resolved after it started: untouched.
        assert _rows(conn, ids["tue2"]) == {
            ids["s2_a"]: ("attended", ids["tue_checked_at"]),
            ids["s2_b"]: ("no_show", None),
        }

        # Mixed session: attended -> checked in (time kept, or stamped now);
        # every no-show on it cleared.
        thu4 = _rows(conn, ids["thu4"])
        walk_status, walk_at = thu4.pop(ids["s4_walk"])
        assert walk_status == "checked_in" and walk_at is not None
        assert thu4 == {ids["s4_early"]: ("checked_in", ids["thu_checked_at"])}

        # Orientation with pre-start audit evidence: repaired like a reopen.
        assert _signup(conn, ids["o_bogus_att"]) == ("checked_in", ids["thu_checked_at"])
        assert _signup(conn, ids["o_bogus_ns"]) == ("confirmed", None)

        # Genuine / unprovable closes keep their results.
        assert set(_rows(conn, ids["thu5"]).values()) == {
            ("attended", ids["thu_checked_at"]), ("no_show", None),
        }
        assert _signup(conn, ids["o_genuine_att"])[0] == "attended"
        assert _signup(conn, ids["o_no_audit_ns"])[0] == "no_show"
        assert _signup(conn, ids["o_mismatch_ns"])[0] == "no_show"
        assert set(_rows(conn, ids["thu6"]).values()) == {
            ("attended", ids["thu_checked_at"]), ("no_show", None),
        }
        assert _signup(conn, ids["o_at_start_ns"])[0] == "no_show"

        audits = conn.execute(
            text(
                "SELECT entity_type, entity_id, actor_id, action, "
                "extra->>'from' AS from_s, extra->>'to' AS to_s, "
                "extra->>'slot_id' AS slot, extra->>'shift_id' AS shift, "
                "extra->>'event_id' AS event, timestamp "
                "FROM audit_logs WHERE extra->>'via' = 'migration_0045'"
            )
        ).all()
        transitions = {
            (a.entity_type, a.entity_id, a.from_s, a.to_s, a.slot, a.shift)
            for a in audits if a.action == "transition"
        }
        assert transitions == {
            ("session_attendance", ids["s2_a"], "no_show", None, ids["thu2"], ids["shift2"]),
            ("session_attendance", ids["s2_b"], "no_show", None, ids["thu2"], ids["shift2"]),
            ("session_attendance", ids["s4_early"], "attended", "checked_in",
             ids["thu4"], ids["shift4"]),
            ("session_attendance", ids["s4_walk"], "attended", "checked_in",
             ids["thu4"], ids["shift4"]),
            ("session_attendance", ids["s4_late_ns"], "no_show", None,
             ids["thu4"], ids["shift4"]),
            ("signup", ids["o_bogus_att"], "attended", "checked_in", None, None),
            ("signup", ids["o_bogus_ns"], "no_show", "confirmed", None, None),
        }
        reopens = {
            (a.entity_type, a.entity_id, a.event)
            for a in audits if a.action == "slot_reopen"
        }
        assert reopens == {
            ("slot", ids["thu2"], ids["kim"]),
            ("slot", ids["thu4"], ids["kim"]),
            ("slot", ids["o_bogus"], ids["kim"]),
        }
        assert len(audits) == len(transitions) + len(reopens)
        assert all(a.actor_id is None and a.timestamp is not None for a in audits)

        # completed_at follows the closed switches again.
        done = dict(conn.execute(text("SELECT id::text, completed_at FROM events")).all())
        assert done[ids["kim"]] is None
        assert done[ids["genuine"]] is None  # drifted, not ours: untouched


def test_0045_downgrade_is_a_no_op_and_rerun_is_stable(alembic_engine, alembic_command):
    ids = _run_to_0044(alembic_engine, alembic_command)
    alembic_command.upgrade(_REV)
    alembic_command.downgrade(_PRE)

    with alembic_engine.connect() as conn:
        # One-way repair: the downgrade does not re-close or restore anything.
        assert not _closed(conn, ids["thu2"])
        assert _rows(conn, ids["thu2"]) == {}

    alembic_command.upgrade(_REV)
    with alembic_engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM audit_logs WHERE extra->>'via' = 'migration_0045'")
        ).scalar() == 10
        assert _closed(conn, ids["thu5"]) and _closed(conn, ids["o_genuine"])
