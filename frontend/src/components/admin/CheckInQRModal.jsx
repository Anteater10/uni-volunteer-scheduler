import React from "react";
import { QRCodeSVG } from "qrcode.react";
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
  if (!open) return null;

  const base = resolveBaseUrl();
  const url = `${base}/event-check-in/${eventId}`;
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
        <div className="flex gap-2 pt-2">
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </Modal>
  );
}
