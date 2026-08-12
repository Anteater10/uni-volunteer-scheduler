import React from "react";
import { X } from "lucide-react";
import ConfirmDialog from "../ui/ConfirmDialog";

/**
 * FormModal — the wide, scrollable shell used by the admin's long forms
 * (New event, Edit event, Event settings).
 *
 * Deliberately separate from components/ui/Modal, which is a narrow
 * max-w-md confirm dialog. This one is sized for a form with sections and
 * keeps its title pinned while the body scrolls.
 *
 * Closing it unmounts its children, and the forms inside hold their state
 * locally — so a close is a data loss, not a navigation. `dirty` lets the form
 * say it has unsaved work; while it is set, every exit route (backdrop,
 * Escape, the X) asks before discarding. The form's own Cancel button is left
 * alone: that one is a labelled, deliberate "throw this away".
 */
export default function FormModal({
  open,
  title,
  subtitle,
  onClose,
  dirty = false,
  children,
}) {
  const [confirmingDiscard, setConfirmingDiscard] = React.useState(false);

  // A close request from anywhere: honoured immediately on a clean form,
  // routed through the discard prompt when there is work to lose.
  const requestClose = React.useCallback(() => {
    if (dirty) {
      setConfirmingDiscard(true);
      return;
    }
    onClose?.();
  }, [dirty, onClose]);

  // Never leave a stale prompt armed for the next opening.
  React.useEffect(() => {
    if (!open) setConfirmingDiscard(false);
  }, [open]);

  // Escape closes it. Clicking the backdrop already did, but a modal that
  // traps Escape leaves keyboard users stuck, and the full-screen overlay
  // silently swallows the next click anywhere on the page.
  React.useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      // While the discard prompt is up it owns Escape — otherwise one keypress
      // would answer the prompt and dismiss the form behind it.
      if (e.key === "Escape" && !confirmingDiscard) requestClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, requestClose, confirmingDiscard]);

  if (!open) return null;
  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 sm:p-6 backdrop-blur-sm animate-fade-in"
        data-testid="form-modal-backdrop"
        // mousedown, not click: a drag that starts in a text field and releases
        // past the panel edge — ordinary text selection — reports its click on
        // the backdrop, and that used to read as "clicked off the dialog".
        onMouseDown={requestClose}
      >
        <div
          className="w-full max-w-5xl max-h-[92vh] overflow-y-auto rounded-2xl bg-white shadow-[0_32px_80px_-16px_rgba(15,23,42,0.45)] ring-1 ring-slate-900/5 animate-pop-in"
          role="dialog"
          aria-modal="true"
          aria-label={typeof title === "string" ? title : undefined}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {/* Tinted header keeps the modal title anchored while the long form
            scrolls underneath it. The gradient hairline on top gives the
            dialog an edge the flat page chrome doesn't have. */}
          <div className="sticky top-0 z-10 overflow-hidden rounded-t-2xl border-b border-[var(--color-border)]">
            <div
              aria-hidden="true"
              className="h-1 w-full bg-gradient-to-r from-[var(--color-brand)] via-sky-400 to-[var(--color-accent)]"
            />
            <div className="flex items-center justify-between gap-4 bg-gradient-to-b from-[var(--color-brand-soft)] to-white px-6 py-4">
              <div className="min-w-0">
                <h2 className="truncate text-xl font-semibold tracking-tight text-[var(--color-fg)]">
                  {title}
                </h2>
                {subtitle ? (
                  <p
                    data-testid="form-modal-subtitle"
                    className="mt-0.5 text-sm text-[var(--color-fg-muted)]"
                  >
                    {subtitle}
                  </p>
                ) : null}
              </div>
              <button
                onClick={requestClose}
                aria-label="Close"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[var(--color-fg-muted)] transition-colors hover:bg-white/80 hover:text-[var(--color-fg)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
          <div className="px-6 py-5">{children}</div>
        </div>
      </div>

      {/* A sibling of the overlay, not a child of it: React bubbles portalled
          events through the React tree, so nesting it here would let a click on
          the prompt's own backdrop also hit this one's mousedown handler. */}
      <ConfirmDialog
        open={confirmingDiscard}
        title="Discard changes?"
        body="This form has changes that haven't been saved. Closing it now loses them."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        onCancel={() => setConfirmingDiscard(false)}
        onConfirm={() => {
          setConfirmingDiscard(false);
          onClose?.();
        }}
      />
    </>
  );
}
