# Signup forms

Every event has a **signup form** — the questions a volunteer answers when they sign up. The form
is a list of fields, and there are two places a form can come from.

**The module's default form** is inherited by events created from that module. Set it once on the
module in Admin → Modules and every new event for that module starts with those questions.

**An event can override the form with its own fields.** Open the form-fields drawer on the event
page in Admin → Events and edit the list. Once an event has its own form, that form wins; the
module default is only used when the event doesn't have one. So the rule is: use the event's own
form if it has one, otherwise use the module's default.

**Changing a form does not change answers already submitted.** Each volunteer's answers are stored
per field against their own signup, so you can still see exactly what each person submitted under
the form that was in force when they signed up.

The volunteer fills the form as part of the signup flow on the event page, after choosing their
slots. If the orientation requirement stops them at that point, **their slot selection and their
form answers are preserved** while they go back to add an orientation session — they don't have to
retype anything.

Form answers are visible to staff on the event roster alongside each volunteer's name, so
information you need at the door (dietary needs, a parking question, whatever the module requires)
should be a form field rather than something collected by email.

There is an older question-and-answer mechanism still present in the system from earlier versions.
New events use the form-fields path described here.
