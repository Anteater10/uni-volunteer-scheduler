# Open Research Questions

Open questions surfaced during exploration or planning that need deeper investigation before they can be locked into a phase or requirement.

---

## Q1: Does the orientation-warning modal check cross-module/cross-week orientation history, or only same-module-same-week?

**Raised:** 2026-04-15 during `/gsd-explore` (v1.3 feature expansion brainstorm)
**Status:** Open
**Blocks:** Phase 15 PART-13 scope decision, and v1.3 Phase 1 (orientation credit engine) design.

**Question in detail:**

The current app ships an orientation-warning modal (PART-02 in v1.2-prod requirements) that fires in the "period-only no-prior-attendance case." We need to know, by reading the code and/or the v1.0/v1.1 phase SUMMARIES, exactly what "no-prior-attendance" is scoped to:

- (a) **Same event only** — "did you sign up for an orientation slot in THIS event?" — wrong for SciTrek's cross-week rule.
- (b) **Same module_template across all events** — "have you ever attended an orientation for this module_template?" — correct for SciTrek.
- (c) **Some other scope** — e.g., same quarter, same week, same campus.

**Why it matters:**

If the answer is (b), the SciTrek cross-week orientation credit rule (see `.planning/notes/2026-04-15-scitrek-orientation-rule.md`) is already respected and v1.3 Phase 1 reduces to polish + edge cases. If the answer is (a) or (c), the orientation engine is a net-new domain feature in v1.3 and should stay on the roadmap as a full phase.

**How to resolve:**

- Read the orientation-related code in `backend/app/` (likely in `signups.py` or a dedicated `orientation.py` service).
- Read v1.0 phase SUMMARIES that introduced orientation-warning (check `.planning/phases/*/` for any mention of orientation).
- Confirm with Andy on a real case: "If I did CRISPR orientation in week 4, does the app suppress the warning when I sign up for CRISPR week 6?"

**Target resolution:** Before v1.2-prod Phase 15 planning finalizes (so PART-13 scope is locked), or at the latest before `/gsd-new-milestone v1.3`.
