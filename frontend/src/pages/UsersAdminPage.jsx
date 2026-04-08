// src/pages/UsersAdminPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";

const ROLES = ["admin", "organizer", "participant"];

export default function UsersAdminPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // Create form
  const [newUser, setNewUser] = useState({
    name: "",
    email: "",
    password: "",
    role: "participant",
    university_id: "",
    notify_email: true,
  });
  const [creating, setCreating] = useState(false);

  // Inline edit state: userId -> partial patch
  const [drafts, setDrafts] = useState({}); // { [id]: { name?, role?, ... } }
  const [savingIds, setSavingIds] = useState({}); // { [id]: true }
  const [query, setQuery] = useState("");

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
    return users.filter((u) => {
      return (
        (u.name || "").toLowerCase().includes(q) ||
        (u.email || "").toLowerCase().includes(q) ||
        (u.role || "").toLowerCase().includes(q) ||
        (u.university_id || "").toLowerCase().includes(q)
      );
    });
  }, [users, query]);

  function setDraft(userId, patch) {
    setDrafts((prev) => ({
      ...prev,
      [userId]: { ...(prev[userId] || {}), ...patch },
    }));
  }

  function getDraftValue(user, field) {
    const d = drafts[user.id] || {};
    return d[field] !== undefined ? d[field] : user[field];
  }

  async function saveUser(userId) {
    const patch = drafts[userId];
    if (!patch || Object.keys(patch).length === 0) return;

    setErr("");
    setSavingIds((p) => ({ ...p, [userId]: true }));
    try {
      const updated = await api.adminUpdateUser(userId, patch);

      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
      setDrafts((prev) => {
        const copy = { ...prev };
        delete copy[userId];
        return copy;
      });
    } catch (e) {
      setErr(e?.message || "Failed to save user");
    } finally {
      setSavingIds((p) => {
        const copy = { ...p };
        delete copy[userId];
        return copy;
      });
    }
  }

  async function deleteUser(userId) {
    const target = users.find((u) => u.id === userId);
    const label = target ? `${target.name || "User"} (${target.email || "no-email"})` : "this user";
    if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;

    setErr("");
    try {
      await api.adminDeleteUser(userId);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      setDrafts((prev) => {
        const copy = { ...prev };
        delete copy[userId];
        return copy;
      });
    } catch (e) {
      setErr(e?.message || "Failed to delete user");
    }
  }

  async function createUser(e) {
    e.preventDefault();
    setErr("");

    if (!newUser.name.trim() || !newUser.email.trim() || !newUser.password.trim()) {
      setErr("Name, email, and password are required.");
      return;
    }

    setCreating(true);
    try {
      const payload = {
        name: newUser.name.trim(),
        email: newUser.email.trim(),
        password: newUser.password,
        role: newUser.role,
        university_id: newUser.university_id?.trim() || null,
        notify_email: !!newUser.notify_email,
      };
      await api.adminCreateUser(payload);

      setNewUser({
        name: "",
        email: "",
        password: "",
        role: "participant",
        university_id: "",
        notify_email: true,
      });

      await load();
    } catch (e2) {
      setErr(e2?.message || "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div style={{ padding: 16, maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>Users (Admin)</h1>
      <p style={{ marginTop: 0, opacity: 0.8 }}>
        Create users and update role/status fields. (Backend: <code>/users</code> admin endpoints)
      </p>

      {err ? (
        <div
          style={{
            background: "rgba(255,0,0,0.08)",
            border: "1px solid rgba(255,0,0,0.25)",
            padding: 12,
            borderRadius: 10,
            marginBottom: 12,
            whiteSpace: "pre-wrap",
          }}
        >
          {err}
        </div>
      ) : null}

      <section style={{ marginBottom: 18 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Create user</h2>
        <form onSubmit={createUser} style={{ display: "grid", gap: 10 }}>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr" }}>
            <label style={{ display: "grid", gap: 6 }}>
              <span>Name</span>
              <input
                value={newUser.name}
                onChange={(e) => setNewUser((p) => ({ ...p, name: e.target.value }))}
                placeholder="Jane Doe"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Email</span>
              <input
                value={newUser.email}
                onChange={(e) => setNewUser((p) => ({ ...p, email: e.target.value }))}
                placeholder="jane@ucsb.edu"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Password</span>
              <input
                value={newUser.password}
                onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))}
                placeholder="Temporary password"
                type="password"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Role</span>
              <select
                value={newUser.role}
                onChange={(e) => setNewUser((p) => ({ ...p, role: e.target.value }))}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>University ID (optional)</span>
              <input
                value={newUser.university_id}
                onChange={(e) => setNewUser((p) => ({ ...p, university_id: e.target.value }))}
                placeholder="Perm / Student ID"
              />
            </label>

            <label style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 24 }}>
              <input
                type="checkbox"
                checked={newUser.notify_email}
                onChange={(e) => setNewUser((p) => ({ ...p, notify_email: e.target.checked }))}
              />
              <span>Notify via email</span>
            </label>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create user"}
            </button>
            <button type="button" onClick={load} disabled={loading}>
              Refresh
            </button>
          </div>
        </form>
      </section>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>All users</h2>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name/email/role..."
            style={{ maxWidth: 320, width: "100%" }}
          />
        </div>

        {loading ? (
          <div>Loading users…</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left" }}>
                  <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Name</th>
                  <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Email</th>
                  <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Role</th>
                  <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>University ID</th>
                  <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Notify</th>
                  <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => {
                  const dirty = !!drafts[u.id];
                  const saving = !!savingIds[u.id];

                  return (
                    <tr key={u.id}>
                      <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        <input
                          value={getDraftValue(u, "name") || ""}
                          onChange={(e) => setDraft(u.id, { name: e.target.value })}
                        />
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        <span style={{ opacity: 0.9 }}>{u.email}</span>
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        <select
                          value={getDraftValue(u, "role") || "participant"}
                          onChange={(e) => setDraft(u.id, { role: e.target.value })}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        <input
                          value={getDraftValue(u, "university_id") || ""}
                          onChange={(e) => setDraft(u.id, { university_id: e.target.value || null })}
                          placeholder="(none)"
                        />
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        <input
                          type="checkbox"
                          checked={!!getDraftValue(u, "notify_email")}
                          onChange={(e) => setDraft(u.id, { notify_email: e.target.checked })}
                        />
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        <div style={{ display: "flex", gap: 10 }}>
                          <button
                            disabled={!dirty || saving}
                            onClick={() => saveUser(u.id)}
                            type="button"
                          >
                            {saving ? "Saving..." : "Save"}
                          </button>
                          <button type="button" onClick={() => deleteUser(u.id)}>
                            Delete
                          </button>
                          {dirty ? (
                            <button
                              type="button"
                              onClick={() =>
                                setDrafts((prev) => {
                                  const copy = { ...prev };
                                  delete copy[u.id];
                                  return copy;
                                })
                              }
                            >
                              Revert
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 12, opacity: 0.8 }}>
                      No users match this search.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
