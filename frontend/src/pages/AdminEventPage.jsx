// AdminEventPage.jsx
import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadBlob } from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  Modal,
  Label,
  Input,
  FieldError,
  EmptyState,
  Skeleton,
} from "../components/ui";
import { toast } from "../state/toast";

export default function AdminEventPage() {
  const { eventId } = useParams();
  const qc = useQueryClient();
  const [privacy, setPrivacy] = useState("full");
  const [confirmExport, setConfirmExport] = useState(false);
  const [err, setErr] = useState("");

  const analyticsQ = useQuery({
    queryKey: ["adminEventAnalytics", eventId],
    queryFn: () => api.admin.eventAnalytics(eventId),
  });

  const rosterQ = useQuery({
    queryKey: ["adminEventRoster", eventId, privacy],
    queryFn: () => api.admin.eventRoster(eventId, privacy),
  });

  const roster = rosterQ.data || [];

  const grouped = useMemo(() => {
    const map = new Map();
    for (const r of roster) {
      const key = r.slot_id;
      if (!map.has(key)) map.set(key, { slot: { id: key, start: r.slot_start, end: r.slot_end }, rows: [] });
      map.get(key).rows.push(r);
    }
    return Array.from(map.values());
  }, [roster]);

  async function doExport() {
    setErr("");
    try {
      await downloadBlob(
        `/admin/events/${eventId}/export?privacy=${privacy}`,
        `event_${eventId}_roster.csv`,
        { auth: true },
      );
      setConfirmExport(false);
      // TODO(copy)
      toast.success("Export ready.");
    } catch (e) {
      setErr(e?.message || "Export failed");
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        /* TODO(copy) */
        title="Admin — Event"
        action={
          <Button variant="danger" onClick={() => setConfirmExport(true)}>
            {/* TODO(copy) */}
            Export CSV
          </Button>
        }
      />

      <Card>
        <div>
          {/* TODO(copy) */}
          <Label htmlFor="privacy">Privacy</Label>
          <select
            id="privacy"
            value={privacy}
            onChange={(e) => setPrivacy(e.target.value)}
            className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
          >
            <option value="full">full</option>
            <option value="minimal">minimal</option>
          </select>
        </div>
        <FieldError>{err}</FieldError>
      </Card>

      <section>
        {/* TODO(copy) */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Analytics
        </h2>
        {analyticsQ.isPending ? (
          <Skeleton className="h-24" />
        ) : analyticsQ.error ? (
          <EmptyState
            /* TODO(copy) */
            title="Couldn't load analytics"
            /* TODO(copy) */
            body={analyticsQ.error.message}
          />
        ) : (
          <Card>
            <pre className="text-xs whitespace-pre-wrap">
              {/* TODO(copy) */}
              {JSON.stringify(analyticsQ.data, null, 2)}
            </pre>
          </Card>
        )}
      </section>

      <section>
        {/* TODO(copy) */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Roster
        </h2>
        {rosterQ.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : rosterQ.error ? (
          <EmptyState
            /* TODO(copy) */
            title="Couldn't load roster"
            /* TODO(copy) */
            body={rosterQ.error.message}
            action={
              <Button onClick={() => qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] })}>
                {/* TODO(copy) */}
                Retry
              </Button>
            }
          />
        ) : grouped.length === 0 ? (
          <EmptyState
            /* TODO(copy) */
            title="No signups yet"
          />
        ) : (
          <div className="space-y-3">
            {grouped.map(({ slot, rows }) => (
              <Card key={slot.id}>
                <p className="text-sm font-medium">
                  {/* TODO(copy) */}
                  Slot: {slot.start} → {slot.end}
                </p>
                <ul className="mt-2 space-y-1">
                  {rows.map((r) => (
                    <li key={r.signup_id || r.id} className="text-sm flex justify-between gap-2">
                      <span>{r.user_name || r.user_email || r.user_id}</span>
                      <span className="text-[var(--color-fg-muted)]">{r.status}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        )}
      </section>

      <Modal
        open={confirmExport}
        onClose={() => setConfirmExport(false)}
        /* TODO(copy) */
        title="Export roster"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Download the current roster as CSV with privacy "{privacy}"?
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setConfirmExport(false)}>
            {/* TODO(copy) */}
            Cancel
          </Button>
          <Button onClick={doExport}>
            {/* TODO(copy) */}
            Download
          </Button>
        </div>
      </Modal>
    </div>
  );
}
