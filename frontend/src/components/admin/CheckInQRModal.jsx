import React from "react";
import { QRCodeSVG } from "qrcode.react";
import { useQuery } from "@tanstack/react-query";
import { fetchRoster } from "../../api/roster";
import { Modal, Button } from "../ui";

function resolveBaseUrl() {
  const configured = import.meta.env.VITE_PUBLIC_BASE_URL;
  if (configured) return configured.replace(/\/$/, "");
  return window.location.origin;
}

function isLocalhostOrigin() {
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "0.0.0.0";
}

export default function CheckInQRModal({ open, onClose, eventId, eventTitle }) {
  // Issue #31 hardening: the QR URL carries the event's venue code (?v=CODE)
  // — the public check-in endpoints gate on it. The roster fetch lazily
  // generates and persists the code server-side, so a first-ever open still
  // resolves one. Hook must run unconditionally (before the !open return).
  const rosterQ = useQuery({
    queryKey: ["qrVenueCode", eventId],
    queryFn: () => fetchRoster(eventId),
    enabled: open && !!eventId,
    staleTime: 60 * 1000,
  });

  if (!open) return null;

  const venueCode = rosterQ.data?.venue_code || null;
  const base = resolveBaseUrl();
  const url = venueCode
    ? `${base}/event-check-in/${eventId}?v=${venueCode}`
    : null;
  const usingConfigured = !!import.meta.env.VITE_PUBLIC_BASE_URL;
  const warnLocalhost = isLocalhostOrigin() && !usingConfigured;

  return (
    <Modal open={open} onClose={onClose} title="Event check-in QR">
      <div className="flex flex-col items-center gap-4">
        <p className="text-sm text-[var(--color-fg-muted)] text-center">
          Volunteers scan this code and enter their email to check in.
          Keep this screen visible at the check-in table.
        </p>
        {eventTitle ? (
          <p className="text-base font-semibold text-center">{eventTitle}</p>
        ) : null}
        {warnLocalhost ? (
          <div className="w-full rounded-md bg-yellow-50 p-2 text-xs text-yellow-900">
            Warning: this QR points at <code>localhost</code> — phones on
            your Wi-Fi can't open it. Set <code>VITE_PUBLIC_BASE_URL</code>
            in <code>frontend/.env.local</code> to your LAN URL (e.g.
            <code>http://192.168.x.x:5173</code>) and restart the dev server.
          </div>
        ) : null}
        {rosterQ.isError ? (
          <div className="w-full rounded-md bg-red-50 p-2 text-sm text-red-900">
            We couldn't load the check-in code for this event. Close and
            reopen this dialog to retry.
          </div>
        ) : url ? (
          <>
            <div className="rounded-lg bg-white p-4">
              <QRCodeSVG value={url} size={256} includeMargin={false} />
            </div>
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs break-all text-[var(--color-fg-muted)] underline"
            >
              {url}
            </a>
            <p className="text-sm text-[var(--color-fg-muted)]">
              Venue code: <strong className="tracking-widest">{venueCode}</strong>
            </p>
          </>
        ) : (
          <p className="text-sm text-[var(--color-fg-muted)]">
            Preparing check-in code…
          </p>
        )}
        <div className="flex gap-2 pt-2">
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </Modal>
  );
}
