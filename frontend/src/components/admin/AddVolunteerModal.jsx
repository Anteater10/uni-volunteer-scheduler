import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Modal, Button, Input, Label, FieldError } from "../ui";
import { api } from "../../lib/api";
import { toast } from "../../state/toast";
import { VENUE_TZ } from "../../lib/venueTime";

// Staff put a volunteer on this event by hand — for someone who emailed
// instead of using the form, or whom the form refused (e.g. booked orientation
// first and came back for the module). The server skips the public-only
// gates (orientation requirement, signup window) on this path.

function fmtWhen(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-US", {
    timeZone: VENUE_TZ,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const EMPTY = { first_name: "", last_name: "", email: "", phone: "" };

export default function AddVolunteerModal({ open, onClose, eventId, event }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [shiftIds, setShiftIds] = useState(() => new Set());
  const [slotIds, setSlotIds] = useState(() => new Set());
  const [allowOverfill, setAllowOverfill] = useState(false);
  const [sendEmail, setSendEmail] = useState(true);
  const [error, setError] = useState("");

  const shifts = event?.shifts || [];
  const orientations = (event?.slots || []).filter(
    (s) => s.slot_type === "orientation",
  );

  function reset() {
    setForm(EMPTY);
    setShiftIds(new Set());
    setSlotIds(new Set());
    setAllowOverfill(false);
    setSendEmail(true);
    setError("");
  }

  function close() {
    reset();
    onClose();
  }

  const mut = useMutation({
    mutationFn: (body) => api.admin.addVolunteer(eventId, body),
    onSuccess: (res) => {
      const waitlisted = (res?.bookings || []).filter(
        (b) => b.status === "waitlisted",
      ).length;
      toast.success(
        waitlisted
          ? `Volunteer added — ${waitlisted} on the waitlist (full).`
          : "Volunteer added.",
      );
      qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] });
      qc.invalidateQueries({ queryKey: ["adminEventAnalytics", eventId] });
      close();
    },
    onError: (e) => setError(e?.message || "Couldn't add the volunteer."),
  });

  function toggle(setter, id) {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function submit(e) {
    e.preventDefault();
    if (!form.first_name.trim() || !form.last_name.trim() || !form.email.trim()) {
      setError("First name, last name and email are required.");
      return;
    }
    if (shiftIds.size === 0 && slotIds.size === 0) {
      setError("Pick at least one shift or orientation session.");
      return;
    }
    setError("");
    mut.mutate({
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim() || null,
      shift_ids: [...shiftIds],
      slot_ids: [...slotIds],
      allow_overfill: allowOverfill,
      send_email: sendEmail,
    });
  }

  const field = (name, label, type = "text") => (
    <div>
      <Label htmlFor={`add-vol-${name}`}>{label}</Label>
      <Input
        id={`add-vol-${name}`}
        type={type}
        value={form[name]}
        onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
      />
    </div>
  );

  const unitRow = (key, checked, onChange, title, detail, full) => (
    <label
      key={key}
      className="flex items-start gap-2 rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
    >
      <input type="checkbox" className="mt-1" checked={checked} onChange={onChange} />
      <span className="min-w-0">
        <span className="font-medium">{title}</span>
        {full ? (
          <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
            Full
          </span>
        ) : null}
        <span className="block text-xs text-[var(--color-fg-muted)]">{detail}</span>
      </span>
    </label>
  );

  return (
    <Modal open={open} onClose={close} title="Add volunteer">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-sm text-[var(--color-fg-muted)]">
          Adds them straight to the roster as confirmed. The orientation
          requirement and signup window don't apply here.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {field("first_name", "First name")}
          {field("last_name", "Last name")}
          {field("email", "Email", "email")}
          {field("phone", "Phone (optional)", "tel")}
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">Shifts</legend>
          {shifts.length === 0 ? (
            <p className="text-sm text-[var(--color-fg-muted)]">No shifts on this event.</p>
          ) : (
            shifts.map((sh) =>
              unitRow(
                sh.id,
                shiftIds.has(sh.id),
                () => toggle(setShiftIds, sh.id),
                sh.name,
                `${(sh.sessions || []).map((s) => fmtWhen(s.start_time)).join(" · ")} — ${sh.current_count}/${sh.capacity}`,
                sh.current_count >= sh.capacity,
              ),
            )
          )}
        </fieldset>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">Orientation sessions</legend>
          {orientations.length === 0 ? (
            <p className="text-sm text-[var(--color-fg-muted)]">
              No orientation sessions on this event.
            </p>
          ) : (
            orientations.map((s) =>
              unitRow(
                s.id,
                slotIds.has(s.id),
                () => toggle(setSlotIds, s.id),
                "Orientation",
                `${fmtWhen(s.start_time)} — ${s.current_count}/${s.capacity}`,
                s.current_count >= s.capacity,
              ),
            )
          )}
        </fieldset>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={allowOverfill}
            onChange={(e) => setAllowOverfill(e.target.checked)}
          />
          If full, seat them anyway (otherwise they go on the waitlist)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={sendEmail}
            onChange={(e) => setSendEmail(e.target.checked)}
          />
          Send them a confirmation email
        </label>

        {error ? <FieldError>{error}</FieldError> : null}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" disabled={mut.isPending}>
            {mut.isPending ? "Adding…" : "Add volunteer"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
