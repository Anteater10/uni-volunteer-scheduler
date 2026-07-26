import React from "react";
import { X } from "lucide-react";

/**
 * FormModal — the wide, scrollable shell used by the admin's long forms
 * (New event, Edit event, Event settings).
 *
 * Deliberately separate from components/ui/Modal, which is a narrow
 * max-w-md confirm dialog. This one is sized for a form with sections and
 * keeps its title pinned while the body scrolls.
 */
export default function FormModal({ open, title, onClose, children }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl max-h-[92vh] overflow-y-auto rounded-2xl bg-white shadow-[0_24px_60px_-12px_rgba(15,23,42,0.35)] ring-1 ring-slate-900/5 animate-pop-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Tinted header keeps the modal title anchored while the long form
            scrolls underneath it. */}
        <div className="sticky top-0 z-10 flex items-center justify-between gap-4 rounded-t-2xl border-b border-[var(--color-border)] bg-gradient-to-b from-[var(--color-brand-soft)] to-white px-6 py-4">
          <h2 className="text-lg font-semibold tracking-tight text-[var(--color-fg)]">
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-fg-muted)] transition-colors hover:bg-white/80 hover:text-[var(--color-fg)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}
