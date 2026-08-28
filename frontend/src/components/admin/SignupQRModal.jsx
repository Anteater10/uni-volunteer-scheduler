import React, { useRef } from "react";
import { QRCodeCanvas } from "qrcode.react";
import { Modal, Button } from "../ui";
import { toast } from "../../state/toast";

// SCRUM-13 (P6) — the *signup* QR. Distinct from CheckInQRModal:
//   check-in QR → /event-check-in/{id}?v={code}, venue-code gated, for
//                 volunteers already signed up, shown at the door only.
//   signup QR   → /volunteer/events/{id}, public, safe to print on a flyer.
// No roster fetch and no credential, so there is nothing async here.

function resolveBaseUrl() {
  const configured = import.meta.env.VITE_PUBLIC_BASE_URL;
  if (configured) return configured.replace(/\/$/, "");
  return window.location.origin;
}

function isLocalhostOrigin() {
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "0.0.0.0";
}

function slugify(text) {
  return (text || "event")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "event";
}

export default function SignupQRModal({
  open,
  onClose,
  eventId,
  eventTitle,
  visibility,
}) {
  const canvasWrapRef = useRef(null);

  if (!open) return null;

  // backend/app/routers/public/events.py:79 allow-lists exactly "public".
  // Anything else — "private", NULL, an unrecognized value — 404s for the
  // volunteer holding the flyer, so we refuse to render a code that leads
  // nowhere rather than let it get printed.
  const isPublic = visibility === "public";

  const base = resolveBaseUrl();
  const url = `${base}/volunteer/events/${eventId}`;
  const usingConfigured = !!import.meta.env.VITE_PUBLIC_BASE_URL;
  const warnLocalhost = isLocalhostOrigin() && !usingConfigured;

  function handleCopy() {
    if (!navigator.clipboard?.writeText) {
      toast.error("Copying isn't available in this browser.");
      return;
    }
    navigator.clipboard
      .writeText(url)
      .then(() => toast.success("Signup link copied."))
      .catch(() => toast.error("Couldn't copy the link."));
  }

  function handleDownload() {
    const canvas = canvasWrapRef.current?.querySelector("canvas");
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `signup-qr-${slugify(eventTitle)}.png`;
    a.click();
  }

  return (
    <Modal open={open} onClose={onClose} title="Signup QR">
      <div className="flex flex-col items-center gap-4">
        <p className="text-sm text-[var(--color-fg-muted)] text-center">
          Anyone who scans this lands on the public signup page for this
          event. Safe to print on a flyer or drop in a slide.
        </p>
        {eventTitle ? (
          <p className="text-base font-semibold text-center">{eventTitle}</p>
        ) : null}

        {!isPublic ? (
          <div className="w-full rounded-md bg-yellow-50 p-3 text-sm text-yellow-900">
            <strong>This event isn't public.</strong> The signup page returns
            "not found" for anyone outside staff, so a printed code would
            scan to a dead end. Set visibility to <strong>Public</strong> in
            Event settings, then reopen this dialog.
          </div>
        ) : (
          <>
            {warnLocalhost ? (
              <div className="w-full rounded-md bg-yellow-50 p-2 text-xs text-yellow-900">
                Warning: this QR points at <code>localhost</code> — phones on
                your Wi-Fi can't open it. Set{" "}
                <code>VITE_PUBLIC_BASE_URL</code> in{" "}
                <code>frontend/.env.local</code> to your LAN URL (e.g.{" "}
                <code>http://192.168.x.x:5173</code>) and restart the dev
                server.
              </div>
            ) : null}
            <div ref={canvasWrapRef} className="rounded-lg bg-white p-4">
              <QRCodeCanvas value={url} size={256} level="M" marginSize={0} />
            </div>
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs break-all text-[var(--color-fg-muted)] underline"
            >
              {url}
            </a>
          </>
        )}

        <div className="flex flex-wrap justify-center gap-2 pt-2">
          {isPublic ? (
            <>
              <Button variant="secondary" onClick={handleCopy}>
                Copy link
              </Button>
              <Button variant="secondary" onClick={handleDownload}>
                Download PNG
              </Button>
            </>
          ) : null}
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </Modal>
  );
}
