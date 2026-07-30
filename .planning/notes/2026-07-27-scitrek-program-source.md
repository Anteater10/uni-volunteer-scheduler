# SciTrek program & policy — raw source from Andy, 2026-07-27

Verbatim capture of Andy's input (appears to be volunteer-orientation slide content).
This is the **only** source for program/policy knowledge that isn't in the code.
`docs/knowledge-base/` docs on program context are written from this file.
Numbers like "5", "7", "8", "13", "14" in the original were slide numbers, not content.

---

## What SciTrek is

- Phenomenon-based, NGSS-aligned curricula.
- Designed by science education experts; grounded in educational, sociocultural, and cognitive science.
- Hands-on engagement: middle and high school students explore a shared phenomenon through
  **5-session modules**.
- STEM mentorship and professional development for scientist-mentors (e.g. Orientation,
  SciTrek Discovery Class).
- Core strength: **meaningful student–mentor interaction**.

## What is a SciTrek module?

- A **5-day science experience** for K-12 students; SciTrek serves **secondary-level** students.
- Each day takes students through a series of activities and experiments examining a particular
  phenomenon.

## How volunteers should mentor ("How we'll do it")

1. Build positive relationships by showing genuine interest, offering praise, and being approachable.
2. Celebrate and recognize accomplishments and genuine attempts.
3. Speak with respect and an expectation of the same. Don't talk down.
4. Stay supportive, focused, and calm.
5. Don't be shy — share yourself (your interests, background, feelings) and don't take anything
   personally.

Also:
- Share your enthusiasm for science and connect with your students.
- Be **collaborative, not directive** — lead as a friend and teammate.
- Stay positive, supportive, and flexible, and remember what it's like to be 12–14 years old.

## What SciTrek offers volunteers

- Science education through community.
- Professional development opportunities.
- Hands-on STEM module development and training.
- Volunteer incentives.
- **Course credit or volunteer hours.**

## Logistics

- **Transportation is provided by SciTrek.**
- **Where to meet:** enter the Main Entrance, walk straight until you hit the bulletin board,
  turn left to **ROOM 1204**.

## Orientation rule (confirmed by Andy)

Orientation is a **hard requirement**.

One edge case: **if no orientation is posted for a module, signing up for an orientation is
optional** for that module. Andy: "99% this should not happen."

> This matches the code exactly — `_ensure_orientation_requirement` exempts events that offer no
> orientation slots (`services/public_signup_service.py:84`), on the grounds that an organizer
> can vouch at the door. So the shipped behavior is the intended policy, not an accident.

---

## Answered by Andy, 2026-07-27

- **Session-by-session signup.** A volunteer does **not** commit to all 5 sessions of a module.
  They sign up session by session and may take as many sessions as they want. This matches the
  app: slots are the bookable unit, and a volunteer picks individual slots within one event.
- **Room 1204 is in the Chemistry building.**
- **Transportation:** nothing for a volunteer to sort out — SciTrek handles it entirely.
- **Course credit** is claimed by **emailing Gulistan**.
- **Contact:** the **SciTrek office for everything**.

## Where to meet (Andy, 2026-07-27 — supersedes the slide text above)

- **Orientation: Chem 1005D**, unless stated otherwise.
- **Module sessions: Chem 1204, 15 minutes before the module starts.**
- The slide directions ("Main Entrance → straight to the bulletin board → left") describe the
  route to **Chem 1204**.

## Staffing and cancellation (Andy, 2026-07-27)

- **Understaffed = below 6 mentors.** This is the threshold Phase B's
  `nudge_understaffed_module` tool should use.
- **Cancellation: give at least 2 days' notice.**

## Contact

- **Gulistan Tansik — gulistan@ucsb.edu.** Course-credit claims go here.
- The **SciTrek office** is the contact for everything else.

## Still missing

- Partner schools and whether anything differs between them.
- What happens after a no-show (any consequence, or just the 2-day-notice expectation?).
- Andy's real chatbot test questions — asked twice, not yet supplied. The FAQ / task-guide docs
  are written from the domain for now and should be extended once those arrive.
