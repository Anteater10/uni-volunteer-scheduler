# Signup forms

Every event has a **signup form** — the questions a volunteer answers when they sign up. The form
is a list of fields, and there are two places a form can come from.

**An event can have its own field list.** Open the form-fields drawer on the event page in Admin →
Events and edit it. Once an event has its own form, that form wins.

**Otherwise the event falls back to its module's default form — and the fallback is live, not a
copy.** Nothing is copied when an event is created. An event with no form of its own always shows
whatever the module's default fields are *right now*, so editing a module default in Admin → Modules
immediately changes the form on every existing event that hasn't overridden it, not just future
ones. That is worth knowing before you edit a default mid-term. If you want one event to differ,
give that event its own field list rather than editing the module.

**A brand-new module starts with an empty default form.** Nothing is pre-seeded — not even the
questions SciTrek usually asks, like emergency contact or t-shirt size. A module you just created
asks volunteers nothing until someone adds fields to it, so add them before its first event goes
live. A *cloned* module is the exception: it inherits its source's fields along with everything
else.

**A field can be one of seven types**: single-line text, long text, dropdown, radio buttons,
checkboxes, phone, and email. Dropdowns, radios, and checkboxes need at least one option. Each field
also needs a short lowercase id (letters, numbers, hyphens and underscores) that is unique within
the form — reusing an id is rejected.

**"Required" is enforced in the volunteer's browser, not by the server.** A volunteer filling in the
public signup form can't submit with a required answer blank. But the server accepts a signup with
required answers missing, on purpose: the organizer is the ultimate authority on who gets to
volunteer, and a staff member adding somebody after the fact should not be blocked by a form field.
So treat required as "the volunteer will be made to answer this", not as a guarantee that every
stored signup has an answer.

**Changing a form does not change answers already submitted.** Each volunteer's answers are stored
per field against their own signup, so you can still see exactly what each person submitted under
the form that was in force when they signed up.

The volunteer fills the form as part of the signup flow on the event page, after choosing their
slots. If the orientation requirement stops them at that point, **their slot selection and their
form answers are preserved** while they go back to add an orientation session — they don't have to
retype anything.

**Form answers appear on the admin event page, not on the roster used at the door.** Each
volunteer's answers show under their name on the event's own page in Admin → Events, and come
through in the roster CSV export. The mobile organizer roster used for check-in does not show them.
So a form field is the right place for things staff want on record and the wrong place for something
someone needs to read off a phone at a classroom door — put that in the event description or send it
to the organizer directly.

There is an older question-and-answer mechanism still present in the system from earlier versions.
New events use the form-fields path described here.
