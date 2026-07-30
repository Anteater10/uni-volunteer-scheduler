# Broadcasts

A **broadcast** is a one-off operational email to the people signed up for an event — the "parking
has moved to Lot 22" message. Both organizers and admins can send one. There are two places to do
it, both using the **Message volunteers** action: the event page in Admin → Events, and the live
roster an organizer is already looking at on the day.

**A broadcast can target the whole event or a single slot.** The default is **All slots**, which
emails everyone signed up for the event. The picker also lists each slot individually, labelled by
kind, date, time, and location, so you can email just Wednesday's group. The picker only appears on
events with more than one slot. The recipient count preview updates as you change the selection, so
you can see who you're about to email before sending.

**Who receives a broadcast:** volunteers who hold or have held a confirmed spot — confirmed, checked
in, and attended. **Waitlisted, pending, cancelled, and no-show volunteers are excluded**, because a
broadcast is instructions for people who are actually coming.

**Someone freshly promoted off the waitlist will miss a broadcast until they confirm.** A promotion
puts the volunteer in the waiting-to-confirm state and gives them three days to claim the spot, and
that state is excluded from the recipient list above. So a broadcast sent during those three days
does not reach them, even though they hold the seat. If a room change lands in that window, contact
them directly.

**Broadcasts ignore reminder preferences.** They're operational, not promotional, so a volunteer
who has turned reminders off still gets told the room changed.

**Broadcasts are rate-limited to five per event per clock hour.** The bucket is a fixed hour on the
clock rather than a rolling window, so the count resets at the top of the hour rather than an hour
after your first send, and the message you get when you hit the limit tells you how long that is. Two
details worth knowing: the limit stays per event even when you target a single slot, because a
per-slot limit would let one event send several times as many emails as it should; and a send that is
refused for hitting the limit still counts against the bucket, so hammering the button after a refusal
does not help.

If you pick a slot that doesn't belong to the event the send is refused — and refused *before* it
counts against your hourly limit, so that particular mistake doesn't cost you a send.

**Each recipient signup gets one copy.** The system records a delivery per signup per broadcast, so a
retry can't double-send. Because the record is per signup rather than per person, a volunteer who
took two sessions in the same event receives two copies of an all-slots broadcast — scope the
broadcast to one slot if that matters.

**The message body is Markdown.** Headings, lists, bold text and links all render, and the compose
box shows a live preview of what you typed. Raw HTML is stripped rather than passed through. Every
broadcast goes out as both an HTML and a plain-text email.

**Every broadcast gets a footer added automatically**, repeating the event's title, time and
location, so you don't need to restate them in the body. The footer also carries a "Manage your
SciTrek signups" link, but that link does not currently work — a volunteer who needs to change a
signup should use the link from their own signup email instead.

**Broadcasts count against the app's daily ceiling on all outbound email.** A large send late in a
busy day can be silently truncated; the reminders document describes that ceiling.

**Every broadcast is recorded in the audit log**, including the subject, the recipient count, who
sent it, and which slot it targeted if you scoped it to one. That is where to look to answer "did
anyone tell them?".
