# Editable Orientation Note Template

**Date:** 2026-04-17
**Status:** Approved
**Milestone:** v1.3 polish

## Problem

The orientation NOTE block on the participant event detail page
(`EventDetailPage.jsx`) is hardcoded SciTrek-specific text:

> You must attend one Orientation. Attending an Orientation before mentoring
> in the classroom is required. ...
> All shifts meet at the SciTrek office in room Chem 1204 and travel by van
> to the school. ...

When rooms, policies, or contact info change, an engineer has to edit source.
Admins can't tune the copy themselves.

A partial fix shipped earlier today (hide the NOTE when the admin writes a
custom description). That covers "I don't want the note at all" but doesn't
solve "I want the same note everywhere, just with Chem 1204 changed to Chem
1179."

## Scope

**In scope:**
- Add an admin-editable global template stored in `site_settings`.
- Surface an editable textarea inside `EventForm` so admins update the template
  while creating/editing an event. No separate settings page.
- Render the current template on every event detail page instead of hardcoded
  strings.

**Out of scope:**
- Per-event overrides. Edit is global.
- Rich-text formatting. Plain text with line breaks only.
- Template versioning / history.
- Multi-template (e.g. by module). One template for all events.

## Approach

Shared global template, always live. Editing the textarea on any event form
and saving the event updates the shared template. Past and future event
detail pages render the newest text — desirable when a room number or contact
address changes.

## Data model

Add one column to existing table:

```python
# backend/app/models.py — SiteSettings
orientation_note_template = Column(
    Text,
    nullable=False,
    default=DEFAULT_ORIENTATION_NOTE,  # current hardcoded text
)
```

Alembic migration: create column, backfill any existing row with
`DEFAULT_ORIENTATION_NOTE`, set `NOT NULL`.

Default text lives in a new module-level constant
`backend/app/defaults.py::DEFAULT_ORIENTATION_NOTE` so both the migration
and the SiteSettings seed use the same string.

## API

Two small endpoints scoped to the existing admin router:

```
GET  /api/v1/admin/settings/orientation-note       → { text: str }
PUT  /api/v1/admin/settings/orientation-note       body: { text: str }
```

`GET` readable by admin + organizer. `PUT` admin-only.

The public event payload (`GET /api/v1/events/{id}` and list) gains one
field:

```json
"orientation_note_text": "You must attend one Orientation. ..."
```

This avoids a second fetch from the participant detail page.

## Frontend — EventForm

Between Description and Slots, a collapsible `<details>` element:

```
▸ Orientation note (shown on event page when orientation slots exist)
```

Expanded state reveals:
- `<textarea>` pre-filled with the current global template.
- Helper text: "This message is shared across all events. Editing it here
  updates the default for every event."

On form submit:
1. If the textarea value differs from the original template loaded at open
   time, `PUT /admin/settings/orientation-note` with the new text.
2. Then the usual event create/update + slot diff.

The template PUT is awaited before the event mutation so a template failure
surfaces as an error. Event mutation still runs on template success.

## Frontend — EventDetailPage

Replace the hardcoded orientation note paragraph with
`event.orientation_note_text`. Keep the existing `hasCustomDescription`
gate: custom description still hides the note text and the logistics /
contact paragraphs, leaves the orientation slot list intact.

## Error handling

- Template `PUT` 403: toast "Only admins can edit the orientation note
  template" and stop before the event mutation.
- Template `PUT` other failure: toast the error, stop. Admin retries.
- Event `GET` missing `orientation_note_text` (old API): fall back to empty
  string; the page still renders without the note. Safe during rolling
  deploy.

## Testing

Backend:
- `test_get_orientation_note_as_admin` returns the current text.
- `test_get_orientation_note_as_organizer` succeeds (read-only).
- `test_put_orientation_note_admin_only` — admin 200, organizer 403.
- `test_put_orientation_note_persists` — subsequent GET reflects PUT.
- `test_event_payload_includes_note_text` — unified event payload carries
  the field.

Frontend (vitest):
- `EventForm` — expander opens, textarea edit dirties, save calls
  `api.adminSettings.putOrientationNote` once with the new value.
- `EventForm` — unchanged textarea does not call the PUT.
- `EventDetailPage` — renders `orientation_note_text` from event payload
  when slots have orientations and description is empty.
- `EventDetailPage` — hides note text when `description` is set.

## Migration & rollout

1. Write + apply Alembic revision adding the column with default backfill.
2. Ship backend with endpoints + payload field.
3. Ship frontend (form expander + detail page consumer).
4. Verify by editing the template on a test event, then load a second event
   and confirm the new text renders.

## Risks

- Retroactive edits affect already-published event pages. That's the
  intended semantic here but worth flagging in the helper text.
- Race: two admins editing simultaneously — last write wins. Acceptable at
  this scale; we log every PUT in the audit trail.
- Rolling deploy: during the gap between backend and frontend ship, the
  frontend may receive events without the new field. Covered by the
  fallback in "Error handling".

## Success criteria

1. Admin opens the EventForm, expands the orientation note, edits text,
   saves. The event saves successfully. A separate event's detail page
   shows the edited text.
2. Organizer cannot save changes (403).
3. All existing event detail pages render the note text from the template
   rather than hardcoded strings.
4. Vitest + pytest suites pass.
