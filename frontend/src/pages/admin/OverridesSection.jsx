// src/pages/admin/OverridesSection.jsx
import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../lib/api";
import {
  Card,
  Button,
  Modal,
  Input,
  Label,
  EmptyState,
  Skeleton,
} from "../../components/ui";
import { toast } from "../../state/toast";

function formatTs(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts || "");
  }
}

export default function OverridesSection() {
  const queryClient = useQueryClient();
  const [filterUser, setFilterUser] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState(null);

  // Create form state
  const [newOverride, setNewOverride] = useState({
    userId: "",
    moduleSlug: "",
    reason: "",
  });

  const overridesQ = useQuery({
    queryKey: ["adminOverrides"],
    queryFn: () => api.admin.overrides.list(),
  });

  const createMut = useMutation({
    mutationFn: () =>
      api.admin.overrides.create(newOverride.userId, {
        module_slug: newOverride.moduleSlug,
        reason: newOverride.reason,
      }),
    onSuccess: () => {
      toast.success("Override created.");
      setShowCreate(false);
      setNewOverride({ userId: "", moduleSlug: "", reason: "" });
      queryClient.invalidateQueries({ queryKey: ["adminOverrides"] });
    },
    onError: (err) => toast.error(err?.message || "Failed to create override"),
  });

  const revokeMut = useMutation({
    mutationFn: (id) => api.admin.overrides.revoke(id),
    onSuccess: () => {
      toast.success("Override revoked.");
      setRevokeTarget(null);
      queryClient.invalidateQueries({ queryKey: ["adminOverrides"] });
    },
    onError: (err) => toast.error(err?.message || "Failed to revoke override"),
  });

  const overrides = overridesQ.data || [];
  const filtered = useMemo(() => {
    if (!filterUser.trim()) return overrides;
    const q = filterUser.trim().toLowerCase();
    return overrides.filter(
      (o) =>
        String(o.user_id || "").toLowerCase().includes(q) ||
        String(o.module_slug || "").toLowerCase().includes(q),
    );
  }, [overrides, filterUser]);

  return (
    <div className="space-y-4">
      {/* Filter + action bar */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-48">
          <Label htmlFor="override-filter">Filter by user ID or module</Label>
          <Input
            id="override-filter"
            value={filterUser}
            onChange={(e) => setFilterUser(e.target.value)}
            placeholder="User ID or module slug"
          />
        </div>
        <Button onClick={() => setShowCreate(true)}>
          {/* TODO(copy) */}
          Create Override
        </Button>
      </div>

      {/* List */}
      {overridesQ.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : overridesQ.error ? (
        <EmptyState
          title="Couldn't load overrides"
          body={overridesQ.error.message}
          action={<Button onClick={() => overridesQ.refetch()}>Retry</Button>}
        />
      ) : filtered.length === 0 ? (
        <EmptyState title="No overrides" body="No prereq overrides match your filter." />
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left">
                  <th className="py-2 pr-3 font-medium">User</th>
                  <th className="py-2 pr-3 font-medium">Module</th>
                  <th className="py-2 pr-3 font-medium">Reason</th>
                  <th className="py-2 pr-3 font-medium">Created</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {filtered.map((o) => (
                  <tr key={o.id}>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {String(o.user_id).slice(0, 8)}
                    </td>
                    <td className="py-2 pr-3">{o.module_slug}</td>
                    <td className="py-2 pr-3 max-w-xs truncate text-[var(--color-fg-muted)]">
                      {o.reason}
                    </td>
                    <td className="py-2 pr-3 text-[var(--color-fg-muted)] whitespace-nowrap">
                      {formatTs(o.created_at)}
                    </td>
                    <td className="py-2 pr-3">
                      {o.revoked_at ? (
                        <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">
                          Revoked
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700">
                          Active
                        </span>
                      )}
                    </td>
                    <td className="py-2">
                      {!o.revoked_at && (
                        <Button
                          variant="danger"
                          className="text-xs !px-2 !py-1"
                          onClick={() => setRevokeTarget(o)}
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

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {filtered.map((o) => (
              <Card key={o.id}>
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-xs">
                    {String(o.user_id).slice(0, 8)}
                  </span>
                  <span className="font-medium">{o.module_slug}</span>
                  {o.revoked_at ? (
                    <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700 ml-auto">
                      Revoked
                    </span>
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700 ml-auto">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-sm text-[var(--color-fg-muted)] mt-1">{o.reason}</p>
                <p className="text-xs text-[var(--color-fg-muted)]">{formatTs(o.created_at)}</p>
                {!o.revoked_at && (
                  <div className="mt-2">
                    <Button
                      variant="danger"
                      className="text-xs !px-2 !py-1"
                      onClick={() => setRevokeTarget(o)}
                    >
                      Revoke
                    </Button>
                  </div>
                )}
              </Card>
            ))}
          </div>
        </>
      )}

      {/* Create Override Modal */}
      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Create Prereq Override"
      >
        <div className="space-y-3">
          <div>
            <Label htmlFor="co-user">User ID</Label>
            <Input
              id="co-user"
              value={newOverride.userId}
              onChange={(e) => setNewOverride((p) => ({ ...p, userId: e.target.value }))}
              placeholder="User UUID"
            />
          </div>
          <div>
            <Label htmlFor="co-module">Module Slug</Label>
            <Input
              id="co-module"
              value={newOverride.moduleSlug}
              onChange={(e) => setNewOverride((p) => ({ ...p, moduleSlug: e.target.value }))}
              placeholder="e.g. orientation-101"
            />
          </div>
          <div>
            <Label htmlFor="co-reason">Reason (min 10 chars)</Label>
            <textarea
              id="co-reason"
              className="w-full min-h-20 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              value={newOverride.reason}
              onChange={(e) => setNewOverride((p) => ({ ...p, reason: e.target.value }))}
              placeholder="Reason for the override"
            />
            <p className="text-xs text-[var(--color-fg-muted)] mt-1">
              {newOverride.reason.length}/10 minimum
            </p>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button
              disabled={
                !newOverride.userId ||
                !newOverride.moduleSlug ||
                newOverride.reason.length < 10 ||
                createMut.isPending
              }
              onClick={() => createMut.mutate()}
            >
              {createMut.isPending ? "Creating..." : "Create Override"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Revoke Confirm Modal */}
      <Modal
        open={!!revokeTarget}
        onClose={() => setRevokeTarget(null)}
        title="Revoke Override"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Revoke the override for module <strong>{revokeTarget?.module_slug}</strong> on user{" "}
          <span className="font-mono">{String(revokeTarget?.user_id || "").slice(0, 8)}</span>?
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setRevokeTarget(null)}>Cancel</Button>
          <Button
            variant="danger"
            disabled={revokeMut.isPending}
            onClick={() => revokeMut.mutate(revokeTarget.id)}
          >
            {revokeMut.isPending ? "Revoking..." : "Revoke"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
