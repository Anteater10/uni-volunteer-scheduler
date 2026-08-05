// Phase 26 — Broadcast messages modal.
//
// Used on AdminEventPage + OrganizerRosterPage. Organizer or admin can
// email all confirmed/checked_in/attended signups on an event with a
// markdown body. Rate-limited to 5/hour/event at the API level.
//
// We keep markdown preview inline and dependency-free — the preview
// only covers the common subset organizers actually use (bold, italic,
// links, bullets, line breaks) and is purely visual; the real render
// happens on the backend before sending.

import React, { useEffect, useMemo, useState } from "react";

import api from "../lib/api";
import { Button, Modal, Label, Input, FieldError } from "./ui";
import { toast } from "../state/toast";

const SUBJECT_MAX = 200;
const BODY_MAX = 20000;

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Tiny-but-safe markdown preview renderer. Only supports:
 *   **bold**, *italic*, [link](url), bullet lists, paragraph breaks.
 * Anything else appears as plain text (HTML-escaped). This is a *preview*
 * only — the backend renders the final email with a real markdown library.
 */
function previewMarkdown(md) {
  if (!md) return "";
  const esc = escapeHtml(md);
  // inline: bold → italic → links
  let inline = esc
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
    );
  // block-level: paragraphs + simple bullets
  const blocks = inline.split(/\n{2,}/);
  const html = blocks
    .map((block) => {
      const lines = block.split(/\n/);
      const bullets = lines.every((l) => /^\s*[-*]\s+/.test(l));
      if (bullets) {
        const items = lines
          .map((l) => l.replace(/^\s*[-*]\s+/, ""))
          .map((t) => `<li>${t}</li>`)
          .join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${lines.join("<br/>")}</p>`;
    })
    .join("");
  return html;
}

/**
 * Slots have no name field — label them by type + date + time + location,
 * mirroring SignupSuccessCard's formatSlotLine (backend timestamps may be
 * naive UTC, so append "Z" before parsing).
 */
function formatSlotOption(slot) {
  const type = slot.slot_type
    ? slot.slot_type.charAt(0).toUpperCase() + slot.slot_type.slice(1)
    : "Slot";
  const date = slot.date
    ? new Date(
        slot.date.includes("T") ? slot.date : `${slot.date}T00:00:00`,
      ).toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      })
    : "";
  const toTime = (ts) =>
    ts
      ? new Date(
          ts.includes("Z") || ts.includes("+") ? ts : `${ts}Z`,
        ).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
      : "";
  const start = toTime(slot.start_time);
  const end = toTime(slot.end_time);
  const timeRange = start && end ? `${start}–${end}` : start;
  return [type, date, timeRange, slot.location].filter(Boolean).join(" · ");
}

/**
 * The things that actually have a roster to email.
 *
 * 2026-08-05 shifts: the picker used to list raw slots, which after shifts
 * means listing *sessions* — and a session has no roster of its own, so every
 * classroom option in the list was unsendable (the API 422s it, naming
 * shift_id). Capacity, the waitlist and the commitment all sit on the shift,
 * so the shift is the unit. Orientation slots are still booked directly and
 * stay in the list as themselves.
 */
function buildUnits(slots, shifts) {
  const units = [];
  for (const shift of shifts || []) {
    const sessions = (shift.sessions || [])
      .slice()
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    const days = sessions
      .map((x) => formatSlotOption({ ...x, slot_type: null }))
      .filter(Boolean);
    units.push({
      key: `shift:${shift.id}`,
      param: { shift_id: shift.id },
      // Sessions in the label because "Tue morning" alone doesn't say which
      // days the volunteer committed to.
      label: [shift.name, days.join(" + ")].filter(Boolean).join(" · "),
    });
  }
  for (const slot of slots || []) {
    // A session's roster is its shift's, and the shift is already listed.
    if (slot.shift_id) continue;
    units.push({
      key: `slot:${slot.id}`,
      param: { slot_id: slot.id },
      label: formatSlotOption(slot),
    });
  }
  return units;
}

export default function BroadcastModal({
  open,
  onClose,
  eventId,
  scope = "admin", // "admin" | "organizer"
}) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const [recipientCount, setRecipientCount] = useState(null);
  const [recipientErr, setRecipientErr] = useState("");
  const [slots, setSlots] = useState(null);
  const [shifts, setShifts] = useState(null);
  // "" = the whole event; otherwise a key from buildUnits.
  const [unitKey, setUnitKey] = useState("");

  const countFetcher = scope === "organizer"
    ? api.organizer.broadcastRecipientCount
    : api.admin.broadcastRecipientCount;
  const sender = scope === "organizer"
    ? api.organizer.sendBroadcast
    : api.admin.sendBroadcast;

  const units = useMemo(
    () => (slots === null && shifts === null ? null : buildUnits(slots, shifts)),
    [slots, shifts],
  );
  const selectedUnit = units?.find((u) => u.key === unitKey) || null;

  useEffect(() => {
    if (!open || !eventId) return undefined;
    let cancelled = false;
    setRecipientErr("");
    setRecipientCount(null);
    (async () => {
      try {
        const r = selectedUnit
          ? await countFetcher(eventId, selectedUnit.param)
          : await countFetcher(eventId);
        if (!cancelled) setRecipientCount(r?.recipient_count ?? 0);
      } catch (e) {
        if (!cancelled) setRecipientErr(e?.message || "Could not load recipient count");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, eventId, scope, unitKey]);

  useEffect(() => {
    if (!open || !eventId) return undefined;
    let cancelled = false;
    (async () => {
      // Both lists, independently: losing one shouldn't hide the other's
      // options. Failing both just means no picker, and the whole-event send
      // still works.
      const [slotRes, shiftRes] = await Promise.all([
        api.listSlots({ event_id: eventId }).catch(() => []),
        api.shifts.list(eventId).catch(() => []),
      ]);
      if (cancelled) return;
      setSlots(Array.isArray(slotRes) ? slotRes : []);
      setShifts(Array.isArray(shiftRes) ? shiftRes : []);
    })();
    return () => {
      cancelled = true;
    };
  }, [open, eventId]);

  useEffect(() => {
    if (!open) {
      // Reset when closing.
      setSubject("");
      setBody("");
      setSending(false);
      setConfirming(false);
      setError("");
      setRecipientCount(null);
      setRecipientErr("");
      setSlots(null);
      setShifts(null);
      setUnitKey("");
    }
  }, [open]);

  const subjectOver = subject.length > SUBJECT_MAX;
  const bodyOver = body.length > BODY_MAX;
  const canSend =
    !sending &&
    subject.trim().length > 0 &&
    body.trim().length > 0 &&
    !subjectOver &&
    !bodyOver;

  const previewHtml = useMemo(() => previewMarkdown(body), [body]);

  async function onSend() {
    setError("");
    setSending(true);
    try {
      const result = await sender(eventId, {
        subject: subject.trim(),
        body_markdown: body,
        ...(selectedUnit ? selectedUnit.param : {}),
      });
      const n = result?.recipient_count ?? 0;
      toast.success(`Broadcast sent to ${n} volunteer${n === 1 ? "" : "s"}.`);
      onClose?.();
    } catch (e) {
      if (e?.status === 429) {
        const wait = e.retryAfter ? `${e.retryAfter}s` : "a bit";
        setError(
          `Rate limit reached (5 broadcasts per hour per event). Try again in ${wait}.`,
        );
      } else {
        setError(e?.message || "Broadcast failed");
      }
    } finally {
      setSending(false);
      setConfirming(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={sending ? () => {} : onClose}
      title="Message volunteers"
      data-testid="broadcast-modal"
      className="max-w-xl"
    >
      <p className="text-sm text-[var(--color-fg-muted)] mb-3">
        Send a one-time email to volunteers signed up for this event
        (confirmed, checked in, or attended) — everyone, or just one shift or
        orientation slot. Rate-limited to 5 broadcasts per hour per event.
      </p>

      {units && units.length >= 2 ? (
        <div className="mb-3">
          <Label htmlFor="broadcast-slot">Send to</Label>
          <select
            id="broadcast-slot"
            data-testid="broadcast-slot-select"
            className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
            value={unitKey}
            onChange={(e) => setUnitKey(e.target.value)}
            disabled={sending}
          >
            <option value="">Everyone signed up for this event</option>
            {units.map((u) => (
              <option key={u.key} value={u.key}>
                {u.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div className="mb-3">
        {recipientErr ? (
          <p className="text-sm text-red-600" role="alert">
            {recipientErr}
          </p>
        ) : recipientCount === null ? (
          <p className="text-sm text-[var(--color-fg-muted)]">
            Loading recipient count…
          </p>
        ) : (
          <p
            className="text-sm font-medium"
            data-testid="broadcast-recipient-count"
          >
            Will send to {recipientCount} volunteer
            {recipientCount === 1 ? "" : "s"}
            {selectedUnit ? " in the selected shift or slot" : ""}.
          </p>
        )}
      </div>

      <div className="mb-3">
        <Label htmlFor="broadcast-subject">Subject</Label>
        <Input
          id="broadcast-subject"
          value={subject}
          maxLength={SUBJECT_MAX + 20}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Parking has moved to Lot 22"
          disabled={sending}
        />
        <p
          className={`mt-1 text-xs ${
            subjectOver
              ? "text-red-600"
              : "text-[var(--color-fg-muted)]"
          }`}
          aria-live="polite"
        >
          {subject.length} / {SUBJECT_MAX}
        </p>
      </div>

      <div className="mb-3">
        <Label htmlFor="broadcast-body">Message (Markdown)</Label>
        <textarea
          id="broadcast-body"
          className="min-h-40 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-base"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Hi team, parking is now at **Lot 22**…"
          disabled={sending}
        />
        <p
          className={`mt-1 text-xs ${
            bodyOver
              ? "text-red-600"
              : "text-[var(--color-fg-muted)]"
          }`}
        >
          {body.length} / {BODY_MAX}
        </p>
      </div>

      <div className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-muted)] mb-1">
          Preview
        </p>
        <div
          data-testid="broadcast-preview"
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-subtle,transparent)] p-3 text-sm"
          // previewHtml is computed from our own safe renderer, which
          // HTML-escapes the input before inline rules run.
          dangerouslySetInnerHTML={{ __html: previewHtml || "<em>Nothing to preview</em>" }}
        />
      </div>

      <FieldError>{error}</FieldError>

      <div className="flex justify-end gap-2 mt-3">
        <Button
          variant="secondary"
          onClick={onClose}
          disabled={sending}
          type="button"
        >
          Cancel
        </Button>
        {confirming ? (
          <Button
            onClick={onSend}
            disabled={!canSend}
            type="button"
            data-testid="broadcast-confirm"
          >
            {sending ? "Sending…" : "Confirm send"}
          </Button>
        ) : (
          <Button
            onClick={() => setConfirming(true)}
            disabled={!canSend}
            type="button"
            data-testid="broadcast-send"
          >
            Send broadcast
          </Button>
        )}
      </div>
    </Modal>
  );
}
