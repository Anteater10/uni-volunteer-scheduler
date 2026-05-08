// src/pages/admin/OrientationCreditsSection.jsx
//
// Phase 21 — admin Orientation Credits page.
//
// Lists explicit orientation_credits rows (signup-based attendance stays
// derived and isn't shown here — admins read attendance on the event roster).
// Supports: grant a credit, revoke a credit, filter by email / family / active.

import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import api from "../../lib/api";
import { useAdminPageTitle } from "./AdminLayout";
import {
  Button,
  Card,
  EmptyState,
  FieldError,
  Input,
  Label,
  Modal,
  Skeleton,
} from "../../components/ui";
import { toast } from "../../state/toast";

function fmtDateTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function SourceBadge({ source }) {
  const cls =
    source === "attendance"
      ? "bg-emerald-100 text-emerald-800"
      : "bg-indigo-100 text-indigo-800";
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full ${cls}`}>
      {source}
    </span>
  );
}

function StatusBadge({ revokedAt }) {
  if (revokedAt) {
    return (
      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-gray-200 text-gray-700">
        revoked
      </span>
    );
  }
  return (
    <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800">
      active
    </span>
  );
}

export default function OrientationCreditsSection() {
  useAdminPageTitle("Orientation Credits");
  const qc = useQueryClient();

  const [filterEmail, setFilterEmail] = useState("");
  const [filterFamily, setFilterFamily] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [showGrant, setShowGrant] = useState(false);
  const [grantForm, setGrantForm] = useState({
    volunteer_email: "",
    family_key: "",
    notes: "",
  });
  const [grantError, setGrantError] = useState("");
  const [revokeTarget, setRevokeTarget] = useState(null);

  const templatesQ = useQuery({
    queryKey: ["admin", "templates", "for-credit"],
    queryFn: () => api.admin.templates.list(),
    // Templates are small; fine to load once.
    staleTime: 5 * 60 * 1000,
  });

  // Derive the set of distinct family_key values from active templates.
  const familyOptions = useMemo(() => {
    const raw = templatesQ.data;
    const list = Array.isArray(raw) ? raw : raw?.items || [];
    const keys = new Set();
    for (const t of list) {
      if (t.deleted_at) continue;
      const key = t.family_key || t.slug;
      if (key) keys.add(key);
    }
    return Array.from(keys).sort();
  }, [templatesQ.data]);

  const creditsQ = useQuery({
    queryKey: [
      "admin",
      "orientationCredits",
      { filterEmail, filterFamily, activeOnly },
    ],
    queryFn: () =>
      api.admin.orientationCredits.list({
        email: filterEmail || undefined,
        family_key: filterFamily || undefined,
        active_only: activeOnly || undefined,
      }),
  });

  const grantMut = useMutation({
    mutationFn: (body) => api.admin.orientationCredits.create(body),
    onSuccess: () => {
      toast.success("Orientation credit granted.");
      setShowGrant(false);
      setGrantForm({ volunteer_email: "", family_key: "", notes: "" });
      setGrantError("");
      qc.invalidateQueries({ queryKey: ["admin", "orientationCredits"] });
    },
    onError: (err) => {
      setGrantError(err?.message || "Failed to grant credit");
    },
  });

  const revokeMut = useMutation({
    mutationFn: (creditId) => api.admin.orientationCredits.revoke(creditId),
    onSuccess: () => {
      toast.success("Orientation credit revoked.");
      setRevokeTarget(null);
      qc.invalidateQueries({ queryKey: ["admin", "orientationCredits"] });
    },
    onError: (err) => {
      toast.error(err?.message || "Revoke failed");
    },
  });

  const credits = creditsQ.data || [];

  function submitGrant(e) {
    e.preventDefault();
    setGrantError("");
    if (!grantForm.volunteer_email || !grantForm.family_key) {
      setGrantError("Email and family are required.");
      return;
    }
    grantMut.mutate({
      volunteer_email: grantForm.volunteer_email.trim().toLowerCase(),
      family_key: grantForm.family_key,
      notes: grantForm.notes || null,
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Orientation Credits</h1>
        <Button onClick={() => setShowGrant(true)}>Grant credit</Button>
      </div>

      <Card>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <Label htmlFor="filter-email">Filter by email</Label>
            <Input
              id="filter-email"
              type="search"
              value={filterEmail}
              placeholder="volunteer@ucsb.edu"
              onChange={(e) => setFilterEmail(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="filter-family">Filter by family</Label>
            <select
              id="filter-family"
              value={filterFamily}
              onChange={(e) => setFilterFamily(e.target.value)}
              className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
            >
              <option value="">All families</option>
              {familyOptions.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)}
                className="h-4 w-4"
              />
              Active only (hide revoked)
            </label>
          </div>
        </div>
      </Card>

      {creditsQ.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : creditsQ.error ? (
        <EmptyState
          title="Couldn't load orientation credits"
          body={creditsQ.error.message}
          action={<Button onClick={() => creditsQ.refetch()}>Try again</Button>}
        />
      ) : credits.length === 0 ? (
        <EmptyState
          title="No orientation credits yet"
          body="Granted credits appear here. Signup-based attendance is shown on the event roster instead."
          action={<Button onClick={() => setShowGrant(true)}>Grant credit</Button>}
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">
                  <th className="py-2 pr-3">Email</th>
                  <th className="py-2 pr-3">Family</th>
                  <th className="py-2 pr-3">Source</th>
                  <th className="py-2 pr-3">Granted by</th>
                  <th className="py-2 pr-3">Granted</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3"></th>
                </tr>
              </thead>
              <tbody>
                {credits.map((c) => (
                  <tr
                    key={c.id}
                    className="border-t border-[var(--color-border)]"
                  >
                    <td className="py-2 pr-3 break-all">{c.volunteer_email}</td>
                    <td className="py-2 pr-3">{c.family_key}</td>
                    <td className="py-2 pr-3">
                      <SourceBadge source={c.source} />
                    </td>
                    <td className="py-2 pr-3">
                      {c.granted_by_label || "—"}
                    </td>
                    <td className="py-2 pr-3">{fmtDateTime(c.granted_at)}</td>
                    <td className="py-2 pr-3">
                      <StatusBadge revokedAt={c.revoked_at} />
                    </td>
                    <td className="py-2 pr-3">
                      {c.revoked_at ? null : (
                        <Button
                          variant="secondary"
                          onClick={() => setRevokeTarget(c)}
                        >
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Modal
        open={showGrant}
        onClose={() => setShowGrant(false)}
        title="Grant orientation credit"
      >
        <form onSubmit={submitGrant} className="space-y-3">
          <div>
            <Label htmlFor="grant-email">Volunteer email</Label>
            <Input
              id="grant-email"
              type="email"
              required
              value={grantForm.volunteer_email}
              onChange={(e) =>
                setGrantForm((f) => ({ ...f, volunteer_email: e.target.value }))
              }
            />
          </div>
          <div>
            <Label htmlFor="grant-family">Module family</Label>
            <select
              id="grant-family"
              required
              value={grantForm.family_key}
              onChange={(e) =>
                setGrantForm((f) => ({ ...f, family_key: e.target.value }))
              }
              className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
            >
              <option value="">Select a family…</option>
              {familyOptions.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="grant-notes">Notes (optional)</Label>
            <Input
              id="grant-notes"
              type="text"
              value={grantForm.notes}
              placeholder="Why this credit was granted"
              onChange={(e) =>
                setGrantForm((f) => ({ ...f, notes: e.target.value }))
              }
            />
          </div>
          <FieldError>{grantError}</FieldError>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowGrant(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={grantMut.isPending}>
              {grantMut.isPending ? "Granting…" : "Grant"}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!revokeTarget}
        onClose={() => setRevokeTarget(null)}
        title="Revoke orientation credit?"
      >
        {revokeTarget && (
          <div className="space-y-3">
            <p className="text-sm">
              This will mark the credit as revoked for{" "}
              <strong>{revokeTarget.volunteer_email}</strong> in the{" "}
              <strong>{revokeTarget.family_key}</strong> family. The volunteer
              will see the warning again on next signup.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setRevokeTarget(null)}>
                Cancel
              </Button>
              <Button
                onClick={() => revokeMut.mutate(revokeTarget.id)}
                disabled={revokeMut.isPending}
              >
                {revokeMut.isPending ? "Revoking…" : "Revoke"}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
