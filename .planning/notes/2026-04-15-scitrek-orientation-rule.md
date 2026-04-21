---
date: "2026-04-15 00:55"
promoted: false
title: "SciTrek cross-module orientation credit rule"
context: "Domain knowledge — belongs outside any single phase because multiple phases (15 participant audit, v1.3 Phase 1 orientation engine) must respect it."
---

# SciTrek orientation credit rule

## The rule (as Hung described during /gsd-explore on 2026-04-15)

SciTrek volunteer modules teach kids and require the volunteer to attend an **orientation** before doing the **teaching block**.

**Same-week pairing (easy case):** When a module runs in a given week, a volunteer must sign up for both the orientation slot and the teaching slot in that week. Checking this is just "did you sign up for an orientation AND a volunteer spot in the same module."

**Cross-week credit (the interesting case):** The same module can recur across multiple weeks (e.g., CRISPR runs week 4 AND week 6). These are separate weekly sign-up pages in the external tool SciTrek uses today. If a volunteer did the CRISPR orientation in week 4, they do **not** need to re-do orientation for CRISPR in week 6 — the week-4 orientation credit carries forward for the same module family.

## Why this matters

- Off-the-shelf per-week sign-up tools cannot model this — each weekly form is isolated. SciTrek admins likely enforce the rule manually today.
- This is the load-bearing domain rule that justifies having a custom app at all. Getting this wrong makes the app worse than the current manual process, not better.
- The current app almost certainly does NOT check cross-week/cross-module orientation history (confirmed? — see open research question in `.planning/research/questions.md`).

## Implementation implications

- Orientation credit is keyed by **(participant, module_family)**, not **(participant, event_id)**.
- A "module family" needs to be a first-class concept — probably `module_templates` (which already exists) is the unit. Each weekly occurrence is an event instantiated from the template.
- The orientation-warning modal (PART-02) needs to query: "has this email/phone/student-id ever attended an orientation for this module_template?" — not just "did they sign up for an orientation in this same event."
- Past-attendance lookup requires stable participant identity across events. The app is loginless (PART requirements lock out participant accounts), so identity is email-based. This needs thinking — what if a student uses two different emails across quarters?

## Open questions

- Is "module family" == `module_template.slug`? Or is it a coarser grouping (e.g., CRISPR-intro and CRISPR-advanced share orientation credit)?
- Does orientation credit expire? (e.g., if you did CRISPR orientation 2 years ago, is it still valid?) Ask Andy.
- What happens when the orientation content changes between quarters? Is pre-change credit still valid?
