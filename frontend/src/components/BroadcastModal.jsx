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

  const countFetcher = scope === "organizer"
    ? api.organizer.broadcastRecipientCount
    : api.admin.broadcastRecipientCount;
  const sender = scope === "organizer"
    ? api.organizer.sendBroadcast
    : api.admin.sendBroadcast;

  useEffect(() => {
    if (!open || !eventId) return undefined;
    let cancelled = false;
    setRecipientErr("");
    setRecipientCount(null);
    (async () => {
      try {
        const r = await countFetcher(eventId);
        if (!cancelled) setRecipientCount(r?.recipient_count ?? 0);
      } catch (e) {
        if (!cancelled) setRecipientErr(e?.message || "Could not load recipient count");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, eventId, scope]);

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
        Send a one-time email to everyone currently signed up for this event
        (confirmed, checked in, or attended). Rate-limited to 5 broadcasts per
        hour per event.
      </p>

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
            {recipientCount === 1 ? "" : "s"}.
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
