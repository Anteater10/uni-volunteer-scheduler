// K32. Keyboard containment for the copilot's overlay layers.
//
// The drawer and the session-rating modal are both dialogs, and neither
// behaved like one: Tab walked straight out into the page behind them,
// Escape did nothing, and closing left focus on whatever the browser
// happened to be pointing at. For a keyboard or screen-reader user that
// is not a rough edge, it is the difference between "a dialog" and "the
// page stopped responding".
//
// Only one trap may be active at a time. Nested layers are handled by the
// caller standing its own trap down (see CopilotDrawer, which deactivates
// while the rating modal or a citation panel is up) rather than by
// stacking listeners and hoping the capture order works out.
import { useEffect, useRef } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

// Deliberately does NOT filter on `offsetParent`, the usual visibility
// test: jsdom never lays anything out, so offsetParent is null for every
// element and the trap would believe every dialog is empty. `hidden` and
// `aria-hidden` cover what we actually render.
export function focusableWithin(root) {
  if (!root) return [];
  return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
    (el) =>
      !el.hasAttribute("hidden") && el.getAttribute("aria-hidden") !== "true",
  );
}

export default function useFocusTrap(
  ref,
  { active, onEscape, restoreFocus = false },
) {
  // Held in a ref so an inline `onEscape={() => ...}` doesn't retrigger the
  // effect on every render — which would re-run the initial focus and yank
  // the caret out of the textarea mid-sentence.
  const escapeRef = useRef(onEscape);
  useEffect(() => {
    escapeRef.current = onEscape;
  });

  useEffect(() => {
    if (!active) return undefined;
    const previous = restoreFocus ? document.activeElement : null;
    const initial = focusableWithin(ref.current);
    (initial[0] || ref.current)?.focus?.();

    function onKeyDown(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        escapeRef.current?.();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusableWithin(ref.current);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const current = document.activeElement;
      if (!ref.current?.contains(current)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && current === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && current === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      // `document.contains` matters when an inner layer and its parent
      // close together — restoring to a node that has already unmounted
      // would drop focus onto <body> and undo the parent's own restore.
      if (
        previous &&
        document.contains(previous) &&
        typeof previous.focus === "function"
      ) {
        previous.focus();
      }
    };
  }, [active, ref, restoreFocus]);
}
