// src/pages/UsersAdminPage.jsx
//
// Phase 16 Plan 05 — Users admin page (ADMIN-18..21 + ADMIN-24 CCPA).
//
// Polished table + side-drawer layout. Fixes the D-43.1 shared-err bug by
// splitting createError / updateError / load error states, uses the invite
// flow (Name + Email + Role only) and soft delete via deactivate/reactivate.

import React, { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAdminPageTitle } from "./admin/AdminLayout";
import SideDrawer from "../components/admin/SideDrawer";
import RoleBadge from "../components/admin/RoleBadge";
import {
  Button,
  Input,
  Label,
  Modal,
  EmptyState,
  Skeleton,
} from "../components/ui";
import { toast } from "../state/toast";
import { useAuth } from "../state/useAuth";

// D-13: only admin + organizer can sign into the admin panel.
const ROLES = ["admin", "organizer"];

const RTF = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
function relativeTime(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSec = Math.round((then - Date.now()) / 1000);
  const absSec = Math.abs(diffSec);
  if (absSec < 60) return RTF.format(diffSec, "second");
  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60) return RTF.format(diffMin, "minute");
  const diffHr = Math.round(diffMin / 60);
  if (Math.abs(diffHr) < 24) return RTF.format(diffHr, "hour");
  const diffDay = Math.round(diffHr / 24);
  if (Math.abs(diffDay) < 30) return RTF.format(diffDay, "day");
  const diffMo = Math.round(diffDay / 30);
  if (Math.abs(diffMo) < 12) return RTF.format(diffMo, "month");
  return RTF.format(Math.round(diffMo / 12), "year");
}
function lastLoginLabel(iso) {
  return iso ? relativeTime(iso) : "Never";
}

function statusPillClass(isActive) {
  return isActive
    ? "bg-green-100 text-green-800"
    : "bg-gray-100 text-gray-700";
}

export default function UsersAdminPage() {
  useAdminPageTitle("Users");
  const { user: currentUser } = useAuth();
  const qc = useQueryClient();

  // SEPARATE error states — fixes the D-43.1 shared-err bug.
  const [createError, setCreateError] = useState(null);
  const [updateError, setUpdateError] = useState(null);

  const [showDeactivated, setShowDeactivated] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [drawerUser, setDrawerUser] = useState(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [ccpaModal, setCcpaModal] = useState(null); // {type, user}

  const listQ = useQuery({
    queryKey: ["adminUsers", { include_inactive: showDeactivated }],
    queryFn: () =>
      api.admin.users.list(
        showDeactivated ? { include_inactive: true } : undefined,
      ),
  });

  const inviteM = useMutation({
    mutationFn: (body) => api.admin.users.invite(body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["adminUsers"] });
      setInviteOpen(false);
      setCreateError(null);
      toast.success(
        `Invite sent to ${vars?.email || "user"} — they'll receive an email with next steps.`,
      );
    },
    onError: (e) => setCreateError(e?.message || "Failed to send invite"),
  });

  const updateM = useMutation({
    mutationFn: ({ id, patch }) => api.admin.users.update(id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminUsers"] });
      setDrawerUser(null);
      setUpdateError(null);
      toast.success("User updated.");
    },
    onError: (e) => setUpdateError(e?.message || "Failed to update"),
  });

  const deactivateM = useMutation({
    mutationFn: (id) => api.admin.users.deactivate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminUsers"] });
      setDrawerUser(null);
      setUpdateError(null);
      toast.success("User deactivated.");
    },
    onError: (e) => setUpdateError(e?.message || "Failed to deactivate"),
  });

  const reactivateM = useMutation({
    mutationFn: (id) => api.admin.users.reactivate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminUsers"] });
      setDrawerUser(null);
      setUpdateError(null);
      toast.success("User reactivated.");
    },
    onError: (e) => setUpdateError(e?.message || "Failed to reactivate"),
  });

  const rawUsers = Array.isArray(listQ.data)
    ? listQ.data
    : listQ.data?.items || [];

  // Client-side filter.
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return rawUsers.filter((u) => {
      if (!showDeactivated && u.is_active === false) return false;
      if (roleFilter !== "all" && u.role !== roleFilter) return false;
      if (!q) return true;
      return (
        (u.name || "").toLowerCase().includes(q) ||
        (u.email || "").toLowerCase().includes(q)
      );
    });
  }, [rawUsers, search, roleFilter, showDeactivated]);

  const activeAdminCount = rawUsers.filter(
    (u) => u.role === "admin" && u.is_active !== false,
  ).length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-5xl font-bold tracking-tight">Users</h1>
          <p className="text-xl text-[var(--color-fg-muted)] mt-3">
            People who can sign into this admin panel. Invite organizers and
            other admins — students don't have accounts.
          </p>
        </div>
        <button
          onClick={() => {
            setCreateError(null);
            setInviteOpen(true);
          }}
          className="px-8 py-4 text-xl font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow"
        >
          Invite user
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-4">
        <input
          id="user-search"
          placeholder="Search name or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[20rem] rounded-xl border border-gray-300 px-5 py-4 text-xl"
        />
        <select
          id="role-filter"
          aria-label="Filter by role"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="rounded-xl border border-gray-300 px-5 py-4 text-xl bg-white"
        >
          <option value="all">All roles</option>
          <option value="admin">Admin</option>
          <option value="organizer">Organizer</option>
        </select>
        <label className="flex items-center gap-2 text-lg">
          <input
            type="checkbox"
            checked={showDeactivated}
            onChange={(e) => setShowDeactivated(e.target.checked)}
            className="h-5 w-5"
          />
          Show deactivated
        </label>
      </div>

      {/* Body: loading / error / empty / table */}
      {listQ.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : listQ.error ? (
        <EmptyState
          title="Couldn't load users"
          body={listQ.error.message}
          action={<Button onClick={() => listQ.refetch()}>Retry</Button>}
        />
      ) : filtered.length === 0 ? (
        <EmptyState title="No users found" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full text-2xl">
            <thead className="bg-gray-50 text-left text-xl uppercase tracking-wide text-gray-600">
              <tr>
                <th className="py-5 px-6">Name</th>
                <th className="py-5 px-6">Email</th>
                <th className="py-5 px-6">Role</th>
                <th className="py-5 px-6">Last login</th>
                <th className="py-5 px-6">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((u) => {
                const inactive = u.is_active === false;
                return (
                  <tr
                    key={u.id}
                    className={`cursor-pointer hover:bg-gray-50 ${
                      inactive ? "opacity-50" : ""
                    }`}
                    onClick={() => {
                      setUpdateError(null);
                      setDrawerUser(u);
                    }}
                  >
                    <td className="py-6 px-6 font-semibold">
                      {u.name || "(no name)"}
                    </td>
                    <td className="py-6 px-6 text-gray-800">{u.email}</td>
                    <td className="py-6 px-6">
                      <RoleBadge role={u.role} />
                    </td>
                    <td className="py-6 px-6 text-gray-600">
                      {lastLoginLabel(u.last_login_at)}
                    </td>
                    <td className="py-6 px-6">
                      <span
                        className={`inline-flex items-center rounded-full px-3 py-1 text-base font-medium ${statusPillClass(
                          !inactive,
                        )}`}
                      >
                        {inactive ? "Deactivated" : "Active"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Invite modal */}
      <Modal
        open={inviteOpen}
        onClose={() => {
          setInviteOpen(false);
          setCreateError(null);
        }}
        title="Invite user"
        className="max-w-2xl p-8"
      >
        <InviteForm
          onSubmit={(body) => inviteM.mutate(body)}
          submitting={inviteM.isPending}
          error={createError}
        />
      </Modal>

      {/* Edit drawer */}
      <SideDrawer
        open={!!drawerUser}
        onClose={() => setDrawerUser(null)}
        title="Edit user"
      >
        {drawerUser && (
          <EditUserForm
            user={drawerUser}
            currentUser={currentUser}
            activeAdminCount={activeAdminCount}
            onSave={(patch) =>
              updateM.mutate({ id: drawerUser.id, patch })
            }
            onDeactivate={() => deactivateM.mutate(drawerUser.id)}
            onReactivate={() => reactivateM.mutate(drawerUser.id)}
            onCcpaExport={() =>
              setCcpaModal({ type: "export", user: drawerUser })
            }
            onCcpaDelete={() =>
              setCcpaModal({ type: "delete", user: drawerUser })
            }
            error={updateError}
            saving={
              updateM.isPending ||
              deactivateM.isPending ||
              reactivateM.isPending
            }
          />
        )}
      </SideDrawer>

      {/* CCPA Export modal */}
      {ccpaModal?.type === "export" && (
        <Modal
          open
          onClose={() => setCcpaModal(null)}
          title="Export personal data"
        >
          <p className="text-sm">
            Download all personal data we have on{" "}
            <strong>{ccpaModal.user.name || ccpaModal.user.email}</strong>.
            This includes their signups, check-ins, and audit trail entries.
            The download is a JSON file.
          </p>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setCcpaModal(null)}>
              Cancel
            </Button>
            <Button
              onClick={async () => {
                try {
                  const data = await api.admin.users.ccpaExport(
                    ccpaModal.user.id,
                    "Admin UI CCPA request",
                  );
                  const blob = new Blob([JSON.stringify(data, null, 2)], {
                    type: "application/json",
                  });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `ccpa-export-${ccpaModal.user.id}.json`;
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                  URL.revokeObjectURL(url);
                  toast.success("CCPA export downloaded.");
                  setCcpaModal(null);
                } catch (e) {
                  toast.error(e?.message || "Export failed");
                }
              }}
            >
              Download
            </Button>
          </div>
        </Modal>
      )}

      {/* CCPA Delete modal */}
      {ccpaModal?.type === "delete" && (
        <CcpaDeleteModal
          user={ccpaModal.user}
          onClose={() => setCcpaModal(null)}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ["adminUsers"] });
            setDrawerUser(null);
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Invite form
// ---------------------------------------------------------------------------

function InviteForm({ onSubmit, submitting, error }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("organizer");

  const fieldClass =
    "w-full rounded-xl border border-gray-300 px-4 py-3 text-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ name, email, role });
      }}
      className="space-y-5"
    >
      <div>
        <label htmlFor="invite-name" className="block text-base font-medium mb-1.5">
          Name
        </label>
        <input
          id="invite-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className={fieldClass}
        />
      </div>
      <div>
        <label htmlFor="invite-email" className="block text-base font-medium mb-1.5">
          Email
        </label>
        <input
          id="invite-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className={fieldClass}
        />
      </div>
      <div>
        <label htmlFor="invite-role" className="block text-base font-medium mb-1.5">
          Role
        </label>
        <select
          id="invite-role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className={`${fieldClass} bg-white`}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r.charAt(0).toUpperCase() + r.slice(1)}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p className="text-base text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      )}
      <p className="text-sm text-[var(--color-fg-muted)]">
        They'll get an email with a link to sign in. If they're new, they'll
        set a password on first login.
      </p>
      <div className="flex justify-end pt-2">
        <button
          type="submit"
          disabled={submitting}
          className="px-6 py-3 text-lg font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow disabled:opacity-50"
        >
          {submitting ? "Sending..." : "Send invite"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Edit user form
// ---------------------------------------------------------------------------

function EditUserForm({
  user,
  currentUser,
  activeAdminCount,
  onSave,
  onDeactivate,
  onReactivate,
  onCcpaExport,
  onCcpaDelete,
  error,
  saving,
}) {
  const [name, setName] = useState(user.name || "");
  const [role, setRole] = useState(user.role);
  const [universityId, setUniversityId] = useState(user.university_id || "");
  const [notifyEmail, setNotifyEmail] = useState(user.notify_email ?? true);

  const isSelf = currentUser?.id === user.id;
  const isLastAdmin =
    user.role === "admin" && activeAdminCount <= 1 && user.is_active !== false;

  const cannotDeactivate = isSelf
    ? "You cannot deactivate your own account"
    : isLastAdmin
    ? "Cannot deactivate the last active admin"
    : null;

  const cannotDemote =
    isSelf && user.role === "admin"
      ? "You cannot demote your own admin account"
      : isLastAdmin
      ? "Cannot demote the last active admin"
      : null;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          name,
          role,
          university_id: universityId,
          notify_email: notifyEmail,
        });
      }}
      className="space-y-3"
    >
      <div>
        <Label htmlFor="edit-name">Name</Label>
        <Input
          id="edit-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div>
        <Label htmlFor="edit-email">Email</Label>
        <Input id="edit-email" value={user.email} disabled />
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          Email can't be changed — delete and reinvite if needed.
        </p>
      </div>
      <div>
        <Label htmlFor="edit-role">Role</Label>
        <select
          id="edit-role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          disabled={!!cannotDemote}
          title={cannotDemote || ""}
          className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base disabled:cursor-not-allowed"
        >
          <option value="admin">Admin</option>
          <option value="organizer" disabled={!!cannotDemote}>
            Organizer{cannotDemote ? ` (${cannotDemote})` : ""}
          </option>
        </select>
      </div>
      <div>
        <Label htmlFor="edit-univ-id">University ID</Label>
        <Input
          id="edit-univ-id"
          value={universityId}
          onChange={(e) => setUniversityId(e.target.value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={notifyEmail}
          onChange={(e) => setNotifyEmail(e.target.checked)}
        />
        Email notifications on
      </label>

      {error && (
        <p className="text-sm text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={saving}>
          Save
        </Button>
        {user.is_active !== false ? (
          <Button
            type="button"
            variant="danger"
            onClick={onDeactivate}
            disabled={!!cannotDeactivate || saving}
            title={cannotDeactivate || ""}
          >
            Deactivate
          </Button>
        ) : (
          <Button type="button" onClick={onReactivate} disabled={saving}>
            Reactivate
          </Button>
        )}
      </div>

      <hr className="my-2 border-[var(--color-border)]" />

      <div className="space-y-2">
        <p className="text-sm font-semibold">CCPA (California privacy rights)</p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" onClick={onCcpaExport}>
            CCPA Data Export
          </Button>
          <Button type="button" variant="danger" onClick={onCcpaDelete}>
            CCPA Delete Account
          </Button>
        </div>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// CCPA Delete modal (type-to-confirm)
// ---------------------------------------------------------------------------

function CcpaDeleteModal({ user, onClose, onDone }) {
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    if (confirm !== user.email) return;
    setBusy(true);
    try {
      await api.admin.users.ccpaDelete(user.id, "Admin UI CCPA request");
      toast.success("User data anonymized (CCPA delete).");
      onClose();
      onDone && onDone();
    } catch (e) {
      toast.error(e?.message || "CCPA delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Permanently delete personal data">
      <p className="text-sm">
        Permanently anonymize <strong>{user.name || user.email}</strong>'s
        account. Their signups and check-ins stay (for audit), but their name,
        email, and phone are replaced with "Anonymized user". This cannot be
        undone.
      </p>
      <div className="mt-3">
        <Label htmlFor="ccpa-confirm">
          Type the user's email to confirm:
        </Label>
        <Input
          id="ccpa-confirm"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder={user.email}
        />
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={confirm !== user.email || busy}
          onClick={handleDelete}
        >
          Delete account
        </Button>
      </div>
    </Modal>
  );
}
