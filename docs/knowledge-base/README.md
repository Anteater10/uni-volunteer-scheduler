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
4. **Self-contained paragraphs, in short documents.** Retrieval returns chunks of roughly 1000
   characters, not documents and not paragraphs. A paragraph shorter than that is never split; instead
   *consecutive* paragraphs are merged together until the run reaches the limit. So a chunk is a run of
   neighbouring paragraphs, it does not carry its document's title, and its boundaries are decided by
   character count rather than by topic. Two consequences: repeat the key term in each paragraph so a
   chunk still makes sense alone, and keep neighbouring paragraphs on the same subject, because they
   will be retrieved as one unit whether or not they belong together.
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
is rule 4 above learned the hard way. Because chunks are runs of consecutive paragraphs cut at a
character count, a document that bundles unrelated topics produces chunks that straddle them: as one
document, the "understaffed" threshold and the course-credit contact ended up merged into chunks that
were mostly about mentoring style, so the best-matching chunk for "how do I get course credit?" was not
the chunk carrying the answer. Retrieval matches chunks, not documents — a document that bundles
unrelated topics can be found and still be useless. Split apart, each of these is short enough that
every one of its chunks is about its own subject.

## Where the corpus comes from

Every `.md` file in this directory is ingested except this README, which is deliberately excluded: it
is authoring instructions and a table of contents, and it used to retrieve as a source for real
questions simply because it names the topics it indexes. Meta-documentation about the corpus does not
belong in the corpus — so nothing you write here reaches the assistant.

Three documents outside this directory are also ingested: `docs/deployment.md`, `docs/demo-runbook.md`,
and `docs/ccpa-policy.md`. They answer deployment, restore, and CCPA-policy questions that nothing here
covers. They are the only non-knowledge-base sources; earlier versions of the corpus pulled from
docstrings and planning documents, which is the bug this directory exists to fix. Adding a
wrong-audience source back would re-create it.
