# Modules

A **module** is a multi-session science experience delivered to a class. SciTrek modules usually run
five sessions, but nothing in the app assumes five. In the SciTrek scheduler the module is the
reusable definition, and each real-world delivery of it — at one school, in one week — is an
**event**. Modules live in **Admin → Modules**. (Older notes sometimes call these "module
templates"; the app now just says modules.)

A module carries a **slug** (its unique id, lowercase letters, numbers and hyphens), a name, a
default capacity, a duration in minutes, a session count, a materials list, a description, a
**family key**, and a **default signup form** for its events.

**Capacity, duration, session count, and materials are reference metadata.** They appear in the
Modules list so staff can see at a glance what a module involves, but they do not seed anything: a
new event's shifts and orientation slots start blank, and capacity is typed in per shift and per
orientation slot. The session count is not even editable on the module form, so modules created
through the UI all read "1 session" whatever the real module runs to. Don't read those numbers as
constraints — the numbers that bind are the ones on the event, on its shifts, and on its
orientation slots.

**There is no separate "orientation module."** Orientation is a property of the **slot**: any event
can include an orientation slot alongside its shifts, and ending that orientation slot is what
grants credit for the event's module family. A shift never grants credit, however many of its
sessions a volunteer attends. Because the orientation slot lives inside the
module's own event, the credit it grants always lands on that module's family.

**Modules do three jobs today.** First, every event must name a live module — the module list is the
gate on what can be scheduled at all, and an event with no module could not be checked for
orientation credit. Second, modules define **module families**, the grouping that decides which
orientation counts for which modules. Third, they hold the **default signup form** that events fall
back on. They are *not* used to import events; events are created manually.

**A new module starts as its own family.** When a module is created, its family key is set to its
own slug, so a brand-new module is a family of one and its orientation credit is checked against
itself. The Modules form has no family field, so this happens automatically and cannot be changed
afterwards.

Modules are **soft-deleted**, not destroyed. Deleting one hides it from the pickers but keeps it
recoverable with Restore, and keeps historical events that reference it intelligible.

Modules can also be **cloned** from the Clone button in a module's drawer, which asks for a slug and
name for the copy and brings across everything else — including the family key. That last part makes
cloning more than a shortcut: it is the only way in the app to make two modules share one
orientation. See the module families document.

The link from an event to its module is the module's **slug**, stored as a plain text label rather
than a strict database reference. That is deliberate — it lets modules and events evolve
independently — and a typo can't get in, because creating or saving an event validates the slug
against the live module list. **The case to watch is deleting a module that events already point
at.** Orientation still resolves the family for those events, so the credit rule keeps working, but
the module's default signup form quietly stops applying — an event relying on that default will
start showing volunteers no questions at all. Restore the module, or give the affected events their
own field list.
