// src/pages/UsersAdminPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  Modal,
  Input,
  Label,
  FieldError,
  EmptyState,
  Skeleton,
} from "../components/ui";
import { toast } from "../state/toast";

const ROLES = ["admin", "organizer", "participant"];

export default function UsersAdminPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newUser, setNewUser] = useState({
    name: "",
    email: "",
    password: "",
    role: "participant",
  });

  // CCPA state
  const [ccpaExportTarget, setCcpaExportTarget] = useState(null);
  const [ccpaDeleteTarget, setCcpaDeleteTarget] = useState(null);
  const [ccpaReason, setCcpaReason] = useState("");
  const [ccpaConfirmed, setCcpaConfirmed] = useState(false);

  async function load() {
    setErr("");
    setLoading(true);
    try {
      const data = await api.adminListUsers();
      setUsers(data || []);
    } catch (e) {
      setErr(e?.message || "Failed to load users");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        (u.name || "").toLowerCase().includes(q) ||
        (u.email || "").toLowerCase().includes(q) ||
        (u.role || "").toLowerCase().includes(q),
    );
  }, [users, query]);

  async function createUser(e) {
    e.preventDefault();
    setErr("");
    setCreating(true);
    try {
      await api.adminCreateUser(newUser);
      setNewUser({ name: "", email: "", password: "", role: "participant" });
      toast.success("User created.");
      load();
    } catch (e2) {
      setErr(e2?.message || "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  async function changeRole(user, role) {
    try {
      await api.adminUpdateUser(user.id, { role });
      toast.success("Role updated.");
      load();
    } catch (e) {
      toast.error(e?.message || "Failed");
    }
  }

  async function doDelete() {
    if (!pendingDelete) return;
    try {
      await api.adminDeleteUser(pendingDelete.id);
      setPendingDelete(null);
      toast.success("User deleted.");
      load();
    } catch (e) {
      toast.error(e?.message || "Failed");
    }
  }

  async function doCcpaExport() {
    if (!ccpaExportTarget || ccpaReason.length < 5) return;
    try {
      const data = await api.admin.users.ccpaExport(ccpaExportTarget.id, ccpaReason);
      // Offer as download
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ccpa-export-${ccpaExportTarget.id}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("CCPA export downloaded.");
      setCcpaExportTarget(null);
      setCcpaReason("");
    } catch (e) {
      toast.error(e?.message || "Export failed");
    }
  }

  async function doCcpaDelete() {
    if (!ccpaDeleteTarget || ccpaReason.length < 5 || !ccpaConfirmed) return;
    try {
      await api.admin.users.ccpaDelete(ccpaDeleteTarget.id, ccpaReason);
      toast.success("User data anonymized (CCPA delete).");
      setCcpaDeleteTarget(null);
      setCcpaReason("");
      setCcpaConfirmed(false);
      load();
    } catch (e) {
      toast.error(e?.message || "CCPA delete failed");
    }
  }

  function isDeleted(u) {
    return !!u.deleted_at;
  }

  return (
    <div className="space-y-4">
      <div>
        {/* TODO(copy) */}
        <Label htmlFor="user-search">Search</Label>
        <Input
          id="user-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Name or email"
        />
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : err ? (
        <EmptyState
          title="Couldn't load users"
          body={err}
          action={<Button onClick={load}>Retry</Button>}
        />
      ) : filtered.length === 0 ? (
        <EmptyState title="No users found" />
      ) : (
        <div className="space-y-3">
          {filtered.map((u) => (
            <Card
              key={u.id}
              className={isDeleted(u) ? "opacity-50" : ""}
            >
              <div className="flex items-baseline gap-2">
                <h3 className="font-semibold">{u.name || u.email}</h3>
                {isDeleted(u) && (
                  <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">
                    [deleted]
                  </span>
                )}
              </div>
              <p className="text-sm text-[var(--color-fg-muted)]">{u.email}</p>
              <p className="text-xs text-[var(--color-fg-muted)] mt-1">
                {/* TODO(copy) */}
                Role: {u.role}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {!isDeleted(u) && (
                  <>
                    <select
                      value={u.role}
                      onChange={(e) => changeRole(u, e.target.value)}
                      className="min-h-11 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-sm"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                    <Button variant="danger" onClick={() => setPendingDelete(u)}>
                      Delete
                    </Button>
                  </>
                )}
                <Button
                  variant="secondary"
                  onClick={() => {
                    setCcpaExportTarget(u);
                    setCcpaReason("");
                  }}
                >
                  {/* TODO(copy) */}
                  CCPA Data Export
                </Button>
                {!isDeleted(u) && (
                  <Button
                    variant="danger"
                    onClick={() => {
                      setCcpaDeleteTarget(u);
                      setCcpaReason("");
                      setCcpaConfirmed(false);
                    }}
                  >
                    {/* TODO(copy) */}
                    CCPA Delete Account
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create user section */}
      <section>
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mt-4 mb-2">
          Create user
        </h2>
        <Card>
          <form onSubmit={createUser} className="space-y-3">
            <div>
              <Label htmlFor="nu-name">Name</Label>
              <Input
                id="nu-name"
                value={newUser.name}
                onChange={(e) => setNewUser((p) => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="nu-email">Email</Label>
              <Input
                id="nu-email"
                type="email"
                value={newUser.email}
                onChange={(e) => setNewUser((p) => ({ ...p, email: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="nu-password">Password</Label>
              <Input
                id="nu-password"
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="nu-role">Role</Label>
              <select
                id="nu-role"
                value={newUser.role}
                onChange={(e) => setNewUser((p) => ({ ...p, role: e.target.value }))}
                className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <FieldError>{err}</FieldError>
            <div className="flex justify-end">
              <Button type="submit" disabled={creating}>
                {creating ? "Creating..." : "Create user"}
              </Button>
            </div>
          </form>
        </Card>
      </section>

      {/* Hard delete modal */}
      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="Delete user"
      >
        <p className="text-sm">
          Delete {pendingDelete?.email}? This can't be undone.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setPendingDelete(null)}>Keep</Button>
          <Button variant="danger" onClick={doDelete}>Delete user</Button>
        </div>
      </Modal>

      {/* CCPA Export modal */}
      <Modal
        open={!!ccpaExportTarget}
        onClose={() => setCcpaExportTarget(null)}
        title="CCPA Data Export"
      >
        <p className="text-sm mb-3">
          {/* TODO(copy) */}
          Export all data for {ccpaExportTarget?.email}? This action will be logged.
        </p>
        <div>
          <Label htmlFor="ccpa-export-reason">Reason (required)</Label>
          <textarea
            id="ccpa-export-reason"
            className="w-full min-h-20 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            value={ccpaReason}
            onChange={(e) => setCcpaReason(e.target.value)}
            placeholder="Reason for data export request (min 5 chars)"
          />
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setCcpaExportTarget(null)}>Cancel</Button>
          <Button disabled={ccpaReason.length < 5} onClick={doCcpaExport}>
            Export Data
          </Button>
        </div>
      </Modal>

      {/* CCPA Delete modal */}
      <Modal
        open={!!ccpaDeleteTarget}
        onClose={() => setCcpaDeleteTarget(null)}
        title="CCPA Delete Account"
      >
        <p className="text-sm mb-3 text-red-600 font-medium">
          {/* TODO(copy) */}
          This will permanently anonymize all personal data for {ccpaDeleteTarget?.email}.
          Signup records will be preserved for analytics but all PII will be removed.
        </p>
        <div>
          <Label htmlFor="ccpa-delete-reason">Reason (required)</Label>
          <textarea
            id="ccpa-delete-reason"
            className="w-full min-h-20 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            value={ccpaReason}
            onChange={(e) => setCcpaReason(e.target.value)}
            placeholder="Reason for deletion request (min 5 chars)"
          />
        </div>
        <label className="flex items-center gap-2 mt-3 text-sm">
          <input
            type="checkbox"
            checked={ccpaConfirmed}
            onChange={(e) => setCcpaConfirmed(e.target.checked)}
          />
          {/* TODO(copy) */}
          I understand this is irreversible
        </label>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setCcpaDeleteTarget(null)}>Cancel</Button>
          <Button
            variant="danger"
            disabled={ccpaReason.length < 5 || !ccpaConfirmed}
            onClick={doCcpaDelete}
          >
            Delete Account
          </Button>
        </div>
      </Modal>
    </div>
  );
}
