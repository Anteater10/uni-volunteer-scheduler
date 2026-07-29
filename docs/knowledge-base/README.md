# SciTrek scheduler knowledge base

Authoritative, user-facing documentation of the SciTrek volunteer scheduler, written for the
**admins and organizers who use it** — not for developers.

This directory is the **primary source for the copilot's retrieval corpus**. It exists because the
corpus used to be built from the codebase itself (docstrings, planning documents, developer
journals), which meant the assistant answered domain questions from engineering artifacts written
for the wrong audience.

## Rules for this directory

1. **Current behavior only.** Describe what the app does today. No history, no "was formerly", no
   planned work presented as real. Features that don't exist belong in `30-not-built.md` so the
   assistant can say "no" confidently.
2. **One concept per document.** A reader — or a retrieval query — should land on exactly one file.
3. **Plain language, staff audience.** No table names, no function names, no file paths. Say
   "signup form", not `form_schema`.
4. **Self-contained paragraphs.** Retrieval returns individual chunks, split on blank lines, and a
   chunk does not carry its document's title. Repeat the key term in each paragraph so a chunk
   still makes sense alone.
5. **Grounded, not guessed.** Behavior claims come from the code; program and policy claims come
   from SciTrek staff. Sources are `.planning/notes/2026-07-27-current-state-map.md` and
   `.planning/notes/2026-07-27-scitrek-program-source.md`.
6. **Update this when behavior changes.** A stale document here is worse than a missing one,
   because the assistant will cite it with confidence.

## Contents

**Core domain** — `01-overview` · `02-glossary` · `03-roles-and-access` · `04-quarters-and-weeks` ·
`05-events` · `06-slots` · `07-modules` · `08-module-families` · `09-orientation` ·
`10-signups-and-statuses` · `11-waitlist` · `12-signup-forms` · `13-volunteers-and-identity`

**Day-of operations** — `14-operations-console` · `15-check-in` · `16-venue-codes-and-qr` ·
`17-ending-a-slot` · `18-rosters`

**Communication** — `19-magic-links` · `20-reminders` · `21-broadcasts` · `22-calendar-invites`

**Staff tooling** — `23-users-and-access` · `24-exports-and-analytics` · `25-audit-logs` ·
`26-settings` · `27-quarter-retrospective`

**Answering people** — `28-task-guides` · `29-troubleshooting` · `30-not-built` ·
`31-about-the-copilot`

**Program and policy** — `32-scitrek-program` · `33-volunteer-guide` · `34-where-to-meet` ·
`35-cancellation-notice` · `36-course-credit-and-hours` · `37-mentors-per-session` ·
`38-who-to-contact`

These five short documents were originally sections of `33-volunteer-guide`, and splitting them out
is rule 4 above learned the hard way. As one document, the "understaffed" threshold and the
course-credit contact were both in its *third* chunk, behind two chunks about mentoring style — so a
question like "how do I get course credit?" retrieved the document, matched the wrong chunk, and the
assistant answered "that isn't documented" while looking straight at the file that documented it.
Retrieval matches chunks, not documents. A document that bundles unrelated topics can be found and
still be useless.
