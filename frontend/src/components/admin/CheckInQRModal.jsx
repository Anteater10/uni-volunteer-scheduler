import React from "react";
import { QRCodeSVG } from "qrcode.react";
import { Modal, Button } from "../ui";

export default function CheckInQRModal({ open, onClose, eventId, eventTitle }) {
  if (!open) return null;
  const url = `${window.location.origin}/event-check-in/${eventId}`;

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
