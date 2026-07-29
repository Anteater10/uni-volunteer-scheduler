# Modules

A **module** is a five-session science experience delivered to a class. In the SciTrek scheduler
the module is the reusable definition, and each real-world delivery of it — at one school, in one
week — is an **event**. Modules live in **Admin → Modules**. (Older notes sometimes call these
"module templates"; the app now just says modules.)

A module carries a **slug** (its unique id, lowercase letters, numbers and hyphens), a name, a
default capacity, a duration in minutes, a session count, a materials list, a description, a
**family key**, and a **default signup form** for its events.

**There is no separate "orientation module."** Orientation is a property of **slots**: any event
can include an orientation slot alongside its regular sessions, and ending that orientation slot is
what grants credit for the event's module family. Because the orientation slot lives inside the
module's own event, the credit it grants always lands on that module's family.

**Modules do two jobs today.** First, they define **module families** — the grouping that decides
which orientation counts for which modules. Second, they hold the **default signup form** that new
events inherit. They are *not* used to import events; events are created manually.

**A new module starts as its own family.** When a module is created, its family key defaults to its
own slug, so a brand-new module is a family of one and its orientation credit is checked against
itself. To let several modules share one orientation, give them the same family key — see the
module families document.

Modules are **soft-deleted**, not destroyed. Deleting one hides it from the pickers but keeps it
recoverable with Restore, and keeps historical events that reference it intelligible. Modules can
also be **cloned** as a starting point for a similar module.

The link from an event to its module is the module's **slug**, stored as a plain text label rather
than a strict database reference. That is deliberate — it lets modules and events evolve
independently — but it means a typo'd or renamed slug can leave an event pointing at a module that
no longer exists. If orientation credit is behaving oddly for one event, check that its module slug
still matches a live module.
