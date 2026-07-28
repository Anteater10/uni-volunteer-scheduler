import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { toast } from "../../state/toast";
import FormModal from "./FormModal";
import { EventForm, applySlotDiff } from "../../pages/admin/EventsSection";

/**
 * EventSettingsModal — reconfigure an event from its own page.
 *
 * Before this, changing a title or a slot time meant leaving the event,
 * finding the row again in the Events list, and clicking Edit. Same form,
 * same save path (metadata PATCH, then the slot diff) — only the entry point
 * is new, so the two surfaces can't drift apart.
 *
 * Props:
 *  - open, onClose
 *  - event: the full event from api.events.get (includes slots)
 */
export default function EventSettingsModal({ open, onClose, event }) {
  const qc = useQueryClient();

  const saveM = useMutation({
    mutationFn: async ({ metadata, slots, initialSlots }) => {
      await api.events.update(event.id, metadata);
      await applySlotDiff(event.id, initialSlots, slots);
    },
    onSuccess: () => {
      // Slot edits move capacity and times, which the summary and the roster
      // both read — refresh all three rather than just the detail record.
      qc.invalidateQueries({ queryKey: ["adminEventDetail", event.id] });
      qc.invalidateQueries({ queryKey: ["adminEventAnalytics", event.id] });
      qc.invalidateQueries({ queryKey: ["adminEventRoster", event.id] });
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      onClose();
      toast.success("Event settings saved.");
    },
    onError: (e) => toast.error(e?.message || "Save failed"),
  });

  if (!open || !event) return null;

  return (
    <FormModal open={open} title="Event settings" onClose={onClose}>
      <EventForm
        mode="edit"
        initial={event}
        onSubmit={(payload) => saveM.mutateAsync(payload)}
        onCancel={onClose}
        submitting={saveM.isPending}
      />
    </FormModal>
  );
}
