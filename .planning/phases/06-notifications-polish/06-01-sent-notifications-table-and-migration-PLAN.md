---
phase: 06
plan: 01
name: sent_notifications table + signup reminder columns + Alembic migration
wave: 1
depends_on: []
files_modified:
  - backend/app/models.py
  - backend/alembic/versions/
autonomous: true
requirements:
  - sent_notifications dedup table with UNIQUE(signup_id, kind)
  - Signup.reminder_24h_sent_at and reminder_1h_sent_at denormalized columns
  - Event.reminder_1h_enabled toggle column
  - Alembic migration that applies cleanly
---

# Plan 06-01: sent_notifications Table & Migration

<objective>
Create the `sent_notifications` dedup table that enforces exactly-once email delivery,
add denormalized `reminder_24h_sent_at` / `reminder_1h_sent_at` columns to `signups`,
and add `Event.reminder_1h_enabled` toggle. Ship an Alembic migration.

Purpose: Phase 6 idempotency depends on INSERT ... ON CONFLICT DO NOTHING against
`sent_notifications` before calling Resend. This plan lays the schema foundation.
Output: New table + columns ready for use by plans 02-04.
</objective>

<must_haves>
- `sent_notifications` table:
  - `id UUID PK DEFAULT gen_random_uuid()`
  - `signup_id UUID FK signups.id NOT NULL`
  - `kind TEXT NOT NULL` (one of: `magic_link`, `reminder_24h`, `reminder_1h`, `cancellation`, `reschedule`)
  - `sent_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `provider_id TEXT NULL` (Resend message id)
  - `UNIQUE(signup_id, kind)` constraint (the dedup key)
- `signups.reminder_24h_sent_at TIMESTAMPTZ NULL`
- `signups.reminder_1h_sent_at TIMESTAMPTZ NULL`
- `events.reminder_1h_enabled BOOLEAN NOT NULL DEFAULT TRUE`
- SQLAlchemy model `SentNotification` in models.py with relationship to Signup
- Alembic migration applies cleanly (upgrade + downgrade)
</must_haves>

<tasks>

<task id="06-01-01" parallel="false">
<action>
Edit `backend/app/models.py`:

1. Add `SentNotification` model:
   ```python
   class SentNotification(Base):
       __tablename__ = "sent_notifications"

       id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
       signup_id = Column(UUID(as_uuid=True), ForeignKey("signups.id"), nullable=False)
       kind = Column(String(32), nullable=False)  # magic_link|reminder_24h|reminder_1h|cancellation|reschedule
       sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
       provider_id = Column(String(255), nullable=True)  # Resend message id

       __table_args__ = (
           Index("uq_sent_notifications_signup_kind", "signup_id", "kind", unique=True),
       )

       signup = relationship("Signup", back_populates="sent_notifications")
   ```

2. Add to `Signup` model:
   - `reminder_24h_sent_at = Column(DateTime(timezone=True), nullable=True)`
   - `reminder_1h_sent_at = Column(DateTime(timezone=True), nullable=True)`
   - `sent_notifications = relationship("SentNotification", back_populates="signup", cascade="all, delete-orphan")`

3. Add to `Event` model:
   - `reminder_1h_enabled = Column(Boolean, nullable=False, default=True, server_default="true")`
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.models import SentNotification, Signup; print('ok')"</automated>
</verify>
<done>SentNotification model and Signup/Event columns defined in ORM.</done>
</task>

<task id="06-01-02" parallel="false">
<action>
Generate and review Alembic migration:
```bash
cd backend && alembic revision --autogenerate -m "phase6_sent_notifications_and_reminder_columns"
```

Verify the migration creates:
- `sent_notifications` table with all columns and unique constraint
- `reminder_24h_sent_at` and `reminder_1h_sent_at` on `signups`
- `reminder_1h_enabled` on `events`

Ensure downgrade drops the table and columns.
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head</automated>
</verify>
<done>Migration round-trips cleanly.</done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-06-01 | Tampering | Duplicate sends bypassing dedup | mitigate | UNIQUE(signup_id, kind) enforced at DB level |
| T-06-02 | Info Disclosure | provider_id leaks Resend internals | accept | Column is admin-only; not exposed in student APIs |
</threat_model>

<verification>
- `python -c "from app.models import SentNotification"` exits 0
- Migration applies and round-trips
- `sent_notifications` table has unique constraint on (signup_id, kind)
</verification>

<success_criteria>
Schema foundation for exactly-once delivery is in place. All subsequent plans can INSERT into sent_notifications with ON CONFLICT DO NOTHING.
</success_criteria>

<output>
After completion, create `.planning/phases/06-notifications-polish/06-01-SUMMARY.md`
</output>
