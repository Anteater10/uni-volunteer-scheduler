# Module families

A **module family** is a set of modules that share one orientation requirement. Orientation credit
is earned and checked **per module family**, never per individual module and never per event. The
grouping is stored on the module as its **family key**.

The point of a module family is that related modules should not each demand their own orientation.
If a CRISPR intro module and a CRISPR advanced module share a family key, a volunteer oriented for
that family can sign up for either one, in any week, in any quarter, without doing orientation
again.

**Cloning is how you put two modules in one family today.** A module's family key is set once, when
the module is created, and the Modules screen has no field for it — so a module created from scratch
is always a family of one, keyed to its own slug. A **cloned** module inherits its source's family
key, which makes Clone the way to add a second module to an existing orientation: open the module
whose orientation you want to reuse, clone it, give the copy its own slug and name, and edit it from
there. Building the family the other way round — creating the module first and grouping it
afterwards — is not something the app can do, so get it right at creation.

**How a family key is resolved for an event:** the event names a module slug, the app looks up that
module, and uses the module's family key. If that module somehow has no family key recorded, the app
falls back to its slug — so a module with no explicit family is simply a family of one either way.

**Two fallbacks exist for events that predate today's rules.** Every event created or edited now
must name a live module, so neither case can be produced any more; they cover older rows only. An
event with no module at all fails closed — with no family there is nothing to check a credit
against, so the answer is "no credit found" rather than "any credit will do." An event whose slug
matches no module uses the raw slug as its family, which at least keeps such events consistent with
themselves. The older behavior, where any orientation credit satisfied a check for an unknown
module, was a bug.

**Credit is recorded against the family key, with no link back to the module.** That is why a
family key is effectively permanent once credits exist behind it: if one were ever changed, every
volunteer oriented under the old key would silently read as un-oriented and be asked to attend
orientation again, and the only fix would be re-granting them by hand from Admin → Orientation
Credits.

There is no separate orientation object that could point at the wrong family: an orientation is a
**slot inside a module's event**, so the credit it grants always lands on that event's module family
by construction.

So if you are adding a new module that should reuse an existing orientation, clone the module whose
orientation it should share rather than posting a new orientation for it. If it genuinely needs its
own orientation, create it fresh — it will be its own family — and include an orientation slot in
its events. An event that offers no orientation slot at all skips the requirement entirely; see the
orientation document for that and the other cases that pass automatically, and for how credit is
granted and revoked.
