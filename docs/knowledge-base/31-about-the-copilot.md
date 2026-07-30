# About the copilot (this assistant)

The copilot is the assistant built into the admin side of the SciTrek scheduler. It's for staff —
organizers and admins — and it answers questions about how the app and the SciTrek program work.

**What it answers from.** The copilot searches a curated knowledge base written for staff — the
documents in this directory, plus the deployment guide, the demo runbook, and the CCPA policy — and
answers from what it finds, showing which documents it drew on. Those three extra documents are
deliberate: they cover deploying and restoring the app and the policy behind CCPA requests, which
nothing in the knowledge base explains. When something isn't covered anywhere, the honest answer is
"that isn't in the knowledge base," not a guess.

**Good things to ask it:** what a term means (event, slot, module family, orientation credit), how a
rule works (who needs orientation, who receives a broadcast, when check-in opens), how to do a task
(set up a quarter, close out a session, promote someone off the waitlist), what an error message
means, and what the app deliberately doesn't do.

**It doesn't know things nobody wrote down.** If a policy exists only in someone's head or in an
email thread, the copilot can't answer it. The fix is to add it to the knowledge base rather than to
ask differently.

**The copilot can't see live data today.** Questions like "how many people are signed up for
Thursday" are about the current state of the database, and the copilot has no access to it — it will
say so rather than guess. Use the roster, the Operations console, or the Exports reports for those.
This is a switch that is currently off rather than a permanent limit: tools for reading live figures
(signup counts for a week, a module's roster, understaffed modules, a volunteer's history) are
written but turned off, and they are not finished enough to turn on. Until that changes, the answer to
a live-data question is a page in the app rather than the copilot. So "the copilot won't show me a
colleague's roster" is not about permissions today — it will not show you your own either.

**Those unfinished lookup tools are also written to be narrower than the app itself, which matters
only once they are switched on.** As drafted, they show an organizer just the events that organizer
created, whereas the app's own event and roster pages let any organizer open any event. Nobody can
run into that difference while the tools are off, and it may not survive being finished, so treat the
app's pages as the authority on what an organizer can see and ignore this until the copilot can
actually look anything up.

**Write actions are being built, not shipped.** Having the copilot actually do things — send a
reminder, nudge an understaffed module, move a participant — is in development behind the same switch
as the live-data tools. If it were on, an action the copilot wanted to take would appear in the chat
as a **"Confirm action"** card showing exactly what it proposes to do, with **Confirm** and **Reject**
buttons, so nothing happens without a person agreeing to it. Today no such card can appear. Treat the
copilot as something that explains and looks things up, and do the doing yourself in the app.

**It remembers useful context about you between sessions.** When a chat session ends — either because
it was closed or because it sat idle for half an hour — the copilot pulls out the stable, useful facts
from that conversation and keeps them as a short note about you, which it reads at the start of your
next session. You can see exactly what it has kept: it's on your own **Settings** page under "What
the copilot has learned about you", with the date it last changed. **"Forget what you know about me"**
on that same card clears the note permanently after a confirmation step, and the next session starts
fresh. This is the answer to "does it remember what I told it last week" — yes, in summary form, and
you can read it and delete it.

**Two limits can cut a conversation short**, and both currently show up in the chat as the same
terse "Stream failed: HTTP 429" message. One is personal: sending messages faster than about ten a
minute trips a per-person pace limit that clears after a minute's wait. The other is a **daily usage
budget shared by the whole organization**: once the day's total is spent, nobody can chat until the
next day begins. That one is worth knowing precisely because it isn't personal — one heavy afternoon
can use up the allowance for everybody, and only an admin changing the app's configuration can raise
it. The troubleshooting document has the how-to-tell-them-apart entry.

**Staff can rate its answers.** Thumbs on individual messages and a rating at the end of a session
feed into Admin → Copilot feedback, where admins and organizers can see how it's performing and which
answers were worst. If it gives a bad answer, rating it is the useful response — that's how the
knowledge base gets fixed.

**Volunteers never see the copilot.** It lives on the staff side only, and a volunteer has no account
to see it from.

**The whole copilot sits behind a feature switch.** When it is turned off for a deployment, the chat
button and the Copilot feedback page both disappear rather than showing an error. A staff member who
can't find the copilot at all is usually on a deployment where it isn't switched on.
