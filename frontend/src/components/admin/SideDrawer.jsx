import React, { useEffect } from "react";

/**
 * SideDrawer — right-side slide-over modal.
 *
 * Props:
 *  - open: boolean
 *  - onClose: () => void
 *  - title: string
 *  - children: React node
 *  - widthClass: Tailwind width class (default: "w-[32rem]")
 */
export default function SideDrawer({
  open,
  onClose,
  title,
  children,
  widthClass = "w-[32rem]",
}) {
  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) {
      if (e.key === "Escape") onClose && onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const titleId = "side-drawer-title";

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        data-testid="side-drawer-backdrop"
        className="absolute inset-0 bg-black/40"
        onClick={() => onClose && onClose()}
      />
      {/* Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`absolute right-0 top-0 h-full ${widthClass} max-w-full bg-white shadow-xl flex flex-col`}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2 id={titleId} className="text-lg font-semibold text-gray-900">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={() => onClose && onClose()}
            className="rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  );
}
