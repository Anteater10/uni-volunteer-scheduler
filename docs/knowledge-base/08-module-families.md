# Module families

A **module family** is a set of modules that share one orientation requirement. Orientation credit
is earned and checked **per module family**, never per individual module and never per event. The
grouping is stored on the module template as its **family key**.

The point of a module family is that related modules should not each demand their own orientation.
If SciTrek runs a CRISPR intro module and a CRISPR advanced module, both can carry the family key
`crispr`. A volunteer who is oriented for `crispr` can sign up for either one, in any week, in any
quarter, without doing orientation again.

**How a family key is resolved for an event:** the event names a module slug, the app looks up that
module template, and uses the template's family key. If the template has no family key set, the
app falls back to the template's own slug as the family — so a module with no explicit family is
simply a family of one. If the event's module slug matches no template at all, the raw slug is used
as the family, which at least keeps such events consistent with themselves.

**An event with no module cannot have orientation credit checked against it.** With no module there
is no family, and a credit only ever exists for a specific family — so the answer is "no credit
found" rather than "any credit will do." This is a deliberate fail-closed rule. The older behavior,
where any orientation credit satisfied a check for an unknown module, was a bug.

**Orientation templates must bind to a real family.** The app will not let you save an orientation
template pointing at a family key that no module actually uses; it rejects the save and lists the
families it knows. This prevents the failure that used to happen silently: an orientation that
credited a family nothing checked against, leaving every volunteer permanently un-oriented for the
module the orientation was actually for.

If you are adding a new module that should reuse an existing orientation, set its family key to
that existing family rather than creating a new orientation. If it genuinely needs its own
orientation, give it its own family and create an orientation template bound to it.
