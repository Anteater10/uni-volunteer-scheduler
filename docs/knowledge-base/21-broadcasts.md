# Broadcasts

A **broadcast** is a one-off operational email to the people signed up for an event — the "parking
has moved to Lot 22" message. Send one from the event page in Admin → Events using the message
volunteers action. Both organizers and admins can send broadcasts.

**A broadcast can target the whole event or a single slot.** The default is **All slots**, which
emails everyone signed up for the event. The picker also lists each slot individually, labelled by
kind, date, time, and location, so you can email just Wednesday's group. The picker only appears on
events with more than one slot. The recipient count preview updates as you change the selection, so
you can see who you're about to email before sending.

**Who receives a broadcast:** volunteers who hold or have held a confirmed spot — confirmed,
checked in, and attended. **Waitlisted, pending, cancelled, and no-show volunteers are excluded**,
because a broadcast is instructions for people who are actually coming.

**Broadcasts ignore reminder preferences.** They're operational, not promotional, so a volunteer
who has turned reminders off still gets told the room changed.

**Broadcasts are rate-limited to 5 per hour per event.** The limit stays per event even when you
target a single slot — a per-slot limit would let one event send five times as many emails as it
should. If you hit the limit you'll be told to wait.

**Each recipient gets one copy.** The system deduplicates per volunteer per broadcast, so a retry
can't double-send.

**Every broadcast is recorded in the audit log**, including which slot it targeted if you scoped it
to one. The message body is written in plain text with light formatting and sent as both an HTML and
a plain-text email.

If you pick a slot that doesn't belong to the event the send is refused — and refused *before* it
counts against your hourly limit, so a mistake doesn't cost you a send.
