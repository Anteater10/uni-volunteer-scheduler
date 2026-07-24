"""Backfill orientation_credits from pre-existing orientation attendance.

Design 2026-07-24 (grant-on-slot-end): explicit ``orientation_credits`` rows
become the ONLY credit source — ``has_orientation_credit`` no longer derives
credit from attended/checked_in orientation signups. Anyone who earned credit
under the old derived rule must keep it, so this migration writes one
``source=attendance`` row per (email, family) for every existing orientation
signup in (attended, checked_in).

``checked_in`` is included deliberately: those volunteers hold working credit
today under the derived rule, and stripping it in the same release that
tightens granting would present as a regression. A wrongly-backfilled person
is one admin revoke away — which is the new workflow anyway.

Idempotent: skips (email, family) pairs that already hold an active credit.
Family resolution mirrors ``orientation_service.family_for_event``:
template row → family_key or slug; no template → the event's raw module_slug;
no module_slug → no family, no credit (fail-closed).

NOTE (merge coordination): on the standalone feature branch this revised
0027 directly; on the integration branch with PR #49 it is repointed after
#49's ``0028_add_show_audit_logs_tab`` so the chain stays linear
(0027 → 0028 → 0029) and Alembic keeps a single head.

Revision ID: 0029_backfill_orientation_attendance_credits
Revises: 0028_add_show_audit_logs_tab
"""
from alembic import op

revision = "0029_backfill_orientation_attendance_credits"
down_revision = "0028_add_show_audit_logs_tab"
branch_labels = None
depends_on = None

BACKFILL_NOTES = "backfill: pre-existing orientation attendance"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO orientation_credits
            (volunteer_email, family_key, source, granted_at, quarter_id, notes)
        SELECT
            sub.email,
            sub.family,
            'attendance'::orientationcreditsource,
            sub.granted_at,
            sub.quarter_id,
            '{BACKFILL_NOTES}'
        FROM (
            SELECT DISTINCT ON (lower(v.email), fam.family)
                   lower(v.email)                  AS email,
                   fam.family                      AS family,
                   COALESCE(s.checked_in_at, now()) AS granted_at,
                   e.quarter_id                    AS quarter_id
            FROM signups s
            JOIN slots sl       ON sl.id = s.slot_id
            JOIN events e       ON e.id = sl.event_id
            JOIN volunteers v   ON v.id = s.volunteer_id
            LEFT JOIN module_templates mt ON mt.slug = e.module_slug
            CROSS JOIN LATERAL (
                SELECT CASE
                    WHEN mt.slug IS NOT NULL
                        THEN COALESCE(NULLIF(mt.family_key, ''), mt.slug)
                    ELSE e.module_slug
                END AS family
            ) fam
            WHERE sl.slot_type::text = 'orientation'
              AND s.status::text IN ('attended', 'checked_in')
              AND fam.family IS NOT NULL
            ORDER BY lower(v.email), fam.family,
                     s.checked_in_at DESC NULLS LAST
        ) sub
        WHERE NOT EXISTS (
            SELECT 1 FROM orientation_credits oc
            WHERE oc.volunteer_email = sub.email
              AND oc.family_key = sub.family
              AND oc.revoked_at IS NULL
        );
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM orientation_credits WHERE notes = '{BACKFILL_NOTES}';"
    )
