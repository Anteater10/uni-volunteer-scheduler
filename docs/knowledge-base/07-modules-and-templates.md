# Modules and module templates

A **module** is a five-session science experience delivered to a class. In the SciTrek scheduler
the reusable definition of a module is a **module template**, and each real-world delivery of that
module — at one school, in one week — is an **event**. Module templates live in Admin → Modules
(the page is `/admin/templates`).

A module template carries a **slug** (its unique id, lowercase letters, numbers and hyphens), a
name, a **type**, a default capacity, a duration in minutes, a session count, a materials list, a
description, a **family key**, and a **default form schema** for signups.

Module templates have three **types**: `module` (a regular teaching module), `orientation` (a
mentor orientation), and `seminar`. The type matters because orientation templates are what tie
into the orientation-credit system, and the app treats them differently when you save one.

**Module templates do two jobs today.** First, they define **module families** — the grouping that
decides which orientation counts for which modules. Second, they hold the **default signup form**
that new events inherit. They are *not* used to import events; events are created manually.

**An orientation template must bind to a real module family.** When you save a template of type
`orientation`, the "Links to module" selection is required, and the server rejects a family key
that doesn't match an existing module family, listing the families it knows about. This rule exists
because the old behavior guessed the family from the slug: naming a template "Biology Orientation"
produced the slug `biology-orientation`, which implied the family `biology` — but the actual module
family was `intro-bio`. That mismatch silently minted orphan credit families that nothing ever
checked against, so volunteers appeared un-oriented forever. The standalone-orientation escape
hatch that allowed it is gone.

Module templates are **soft-deleted**, not destroyed. Deleting one hides it from the pickers but
keeps it recoverable with Restore, and keeps historical events that reference it intelligible.
Templates can also be **cloned** as a starting point for a similar module.

The link from an event to its module is the module's **slug**, stored as a plain text label rather
than a strict database reference. That is deliberate — it lets modules and events evolve
independently — but it means a typo'd or renamed slug can leave an event pointing at a module that
no longer exists. If orientation credit is behaving oddly for one event, check that its module slug
still matches a live template.
