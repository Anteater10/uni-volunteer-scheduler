/**
 * Canonical event-title format (SCRUM-154).
 *
 * Every event is named `Week {N} - {Module Name} - {School}`. This is the one
 * place the rule is written down on the frontend. The backend mirror lives in
 * `backend/app/event_title.py`, which is what the copilot's event tools
 * validate against — change both together.
 *
 * Titles created before this rule are left as-is; nothing is backfilled.
 */

/** `Week 7 - Conservation of Mass - GVJH` — single space, hyphen, single space. */
export const EVENT_TITLE_PATTERN = /^Week \d+ - .+ - .+$/;

export const EVENT_TITLE_FORMAT_HINT =
  'Title must match "Week {N} - {Module Name} - {School}" — for example "Week 7 - Conservation of Mass - GVJH".';

/** True if `title` matches the canonical format, ignoring outer whitespace. */
export function isValidEventTitle(title) {
  return EVENT_TITLE_PATTERN.test((title || "").trim());
}
