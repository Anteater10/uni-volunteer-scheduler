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
      // TODO(copy)
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
      // TODO(copy)
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
      // TODO(copy)
      toast.success("User deleted.");
      load();
    } catch (e) {
      toast.error(e?.message || "Failed");
    }
  }

  return (
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="Users" />

      <div>
        {/* TODO(copy) */}
        <Label htmlFor="user-search">Search</Label>
        <Input
          id="user-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          /* TODO(copy) */
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
          /* TODO(copy) */
          title="Couldn't load users"
          /* TODO(copy) */
          body={err}
          action={
            <Button onClick={load}>
              {/* TODO(copy) */}
              Retry
            </Button>
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          /* TODO(copy) */
          title="No users found"
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((u) => (
            <Card key={u.id}>
              <h3 className="font-semibold">{u.name || u.email}</h3>
              <p className="text-sm text-[var(--color-fg-muted)]">{u.email}</p>
              <p className="text-xs text-[var(--color-fg-muted)] mt-1">
                {/* TODO(copy) */}
                Role: {u.role}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <select
                  value={u.role}
                  onChange={(e) => changeRole(u, e.target.value)}
                  className="min-h-11 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-sm"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                <Button variant="danger" onClick={() => setPendingDelete(u)}>
                  {/* TODO(copy) */}
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <section>
        {/* TODO(copy) */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mt-4 mb-2">
          Create user
        </h2>
        <Card>
          <form onSubmit={createUser} className="space-y-3">
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="nu-name">Name</Label>
              <Input
                id="nu-name"
                value={newUser.name}
                onChange={(e) => setNewUser((p) => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="nu-email">Email</Label>
              <Input
                id="nu-email"
                type="email"
                value={newUser.email}
                onChange={(e) => setNewUser((p) => ({ ...p, email: e.target.value }))}
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="nu-password">Password</Label>
              <Input
                id="nu-password"
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))}
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="nu-role">Role</Label>
              <select
                id="nu-role"
                value={newUser.role}
                onChange={(e) => setNewUser((p) => ({ ...p, role: e.target.value }))}
                className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <FieldError>{err}</FieldError>
            <div className="flex justify-end">
              <Button type="submit" disabled={creating}>
                {/* TODO(copy) */}
                {creating ? "Creating..." : "Create user"}
              </Button>
            </div>
          </form>
        </Card>
      </section>

      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        /* TODO(copy) */
        title="Delete user"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Delete {pendingDelete?.email}? This can't be undone.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setPendingDelete(null)}>
            {/* TODO(copy) */}
            Keep
          </Button>
          <Button variant="danger" onClick={doDelete}>
            {/* TODO(copy) */}
            Delete user
          </Button>
        </div>
      </Modal>
    </div>
  );
}
