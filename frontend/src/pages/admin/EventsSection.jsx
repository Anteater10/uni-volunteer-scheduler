import React, { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useAdminPageTitle } from "./AdminLayout";
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

// HTML datetime-local needs "YYYY-MM-DDTHH:MM" with no timezone.
function isoToLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function localInputToIso(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

const EMPTY_FORM = {
  title: "",
  description: "",
  location: "",
  start_date: "",
  end_date: "",
  max_signups_per_user: "",
  visibility: "public",
};

function EventForm({ initial, onSubmit, onCancel, submitting }) {
  const [form, setForm] = useState(() => ({
    ...EMPTY_FORM,
    ...(initial || {}),
    start_date: isoToLocalInput(initial?.start_date),
    end_date: isoToLocalInput(initial?.end_date),
    max_signups_per_user: initial?.max_signups_per_user ?? "",
  }));
  const [error, setError] = useState(null);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!form.title.trim()) return setError("Title is required.");
    if (!form.start_date || !form.end_date)
      return setError("Start and end times are required.");
    if (new Date(form.end_date) <= new Date(form.start_date))
      return setError("End time must be after start time.");

    const payload = {
      title: form.title.trim(),
      description: form.description?.trim() || null,
      location: form.location?.trim() || null,
      visibility: form.visibility || "public",
      start_date: localInputToIso(form.start_date),
      end_date: localInputToIso(form.end_date),
      max_signups_per_user: form.max_signups_per_user
        ? Number(form.max_signups_per_user)
        : null,
    };
    try {
      await onSubmit(payload);
    } catch (err) {
      setError(err?.message || "Save failed");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1">Title *</label>
        <input
          value={form.title}
          onChange={(e) => update("title", e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Description</label>
        <textarea
          value={form.description || ""}
          onChange={(e) => update("description", e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Location</label>
        <input
          value={form.location || ""}
          onChange={(e) => update("location", e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">Start *</label>
          <input
            type="datetime-local"
            value={form.start_date}
            onChange={(e) => update("start_date", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">End *</label>
          <input
            type="datetime-local"
            value={form.end_date}
            onChange={(e) => update("end_date", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">
            Max signups per volunteer
          </label>
          <input
            type="number"
            min="1"
            value={form.max_signups_per_user}
            onChange={(e) => update("max_signups_per_user", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="No limit"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Visibility</label>
          <select
            value={form.visibility}
            onChange={(e) => update("visibility", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="public">Public</option>
            <option value="private">Private</option>
          </select>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function ConfirmDialog({ open, title, body, onCancel, onConfirm, confirmLabel = "Delete", busy }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg max-w-md w-full p-6 shadow-xl">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-gray-600 mt-2">{body}</p>
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg disabled:opacity-50"
          >
            {busy ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function Modal({ open, title, onClose, children }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center rounded-t-xl">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-700 text-2xl leading-none w-8 h-8 flex items-center justify-center rounded hover:bg-gray-100"
          >
            ×
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

export default function EventsSection() {
  useAdminPageTitle("Events");
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("upcoming"); // upcoming | past | all
  const [drawerMode, setDrawerMode] = useState(null); // "create" | "edit"
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const q = useQuery({
    queryKey: ["adminEventsList"],
    queryFn: () => api.events.list(),
  });

  const events = q.data || [];

  const filtered = useMemo(() => {
    const now = Date.now();
    const term = search.toLowerCase().trim();
    return events
      .filter((e) => {
        if (scope === "upcoming" && new Date(e.end_date).getTime() < now) return false;
        if (scope === "past" && new Date(e.end_date).getTime() >= now) return false;
        if (term && !(e.title || "").toLowerCase().includes(term)) return false;
        return true;
      })
      .sort((a, b) => new Date(a.start_date) - new Date(b.start_date));
  }, [events, search, scope]);

  const createM = useMutation({
    mutationFn: (payload) => api.events.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      setDrawerMode(null);
      toast.success("Event created.");
    },
  });

  const updateM = useMutation({
    mutationFn: ({ id, payload }) => api.events.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      setDrawerMode(null);
      setEditing(null);
      toast.success("Event updated.");
    },
  });

  const deleteM = useMutation({
    mutationFn: (id) => api.events.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      setDeleting(null);
      toast.success("Event deleted.");
    },
    onError: (e) => toast.error(e?.message || "Delete failed"),
  });

  const cloneM = useMutation({
    mutationFn: (id) => api.events.clone(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      toast.success("Event cloned.");
    },
    onError: (e) => toast.error(e?.message || "Clone failed"),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Events</h1>
          <p className="text-sm text-gray-600">
            All events in the system. Create, edit, or delete events here.
          </p>
        </div>
        <button
          onClick={() => {
            setEditing(null);
            setDrawerMode("create");
          }}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg"
        >
          + New event
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          placeholder="Search by title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[14rem] rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white"
        >
          <option value="upcoming">Upcoming</option>
          <option value="past">Past</option>
          <option value="all">All</option>
        </select>
      </div>

      {q.isPending ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : q.error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Couldn't load events: {q.error.message}{" "}
          <button onClick={() => q.refetch()} className="underline ml-2">
            Retry
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-600">
          No events match.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="py-2 px-3">Title</th>
                <th className="py-2 px-3">Start</th>
                <th className="py-2 px-3">End</th>
                <th className="py-2 px-3">Location</th>
                <th className="py-2 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="py-2 px-3 font-medium">
                    <Link
                      to={`/admin/events/${e.id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {e.title || "(untitled)"}
                    </Link>
                  </td>
                  <td className="py-2 px-3">{fmtDateTime(e.start_date)}</td>
                  <td className="py-2 px-3">{fmtDateTime(e.end_date)}</td>
                  <td className="py-2 px-3">{e.location || "—"}</td>
                  <td className="py-2 px-3 text-right space-x-2 whitespace-nowrap">
                    <button
                      onClick={() => {
                        setEditing(e);
                        setDrawerMode("edit");
                      }}
                      className="text-blue-600 hover:underline"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => cloneM.mutate(e.id)}
                      className="text-gray-700 hover:underline"
                    >
                      Clone
                    </button>
                    <button
                      onClick={() => setDeleting(e)}
                      className="text-red-600 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={drawerMode === "create"}
        title="New event"
        onClose={() => setDrawerMode(null)}
      >
        <EventForm
          onSubmit={(payload) => createM.mutateAsync(payload)}
          onCancel={() => setDrawerMode(null)}
          submitting={createM.isPending}
        />
      </Modal>

      <Modal
        open={drawerMode === "edit"}
        title="Edit event"
        onClose={() => {
          setDrawerMode(null);
          setEditing(null);
        }}
      >
        {editing && (
          <EventForm
            initial={editing}
            onSubmit={(payload) =>
              updateM.mutateAsync({ id: editing.id, payload })
            }
            onCancel={() => {
              setDrawerMode(null);
              setEditing(null);
            }}
            submitting={updateM.isPending}
          />
        )}
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        title="Delete event?"
        body={`This will permanently delete "${deleting?.title}" and its slots. Existing signups will be removed. This cannot be undone.`}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleteM.mutate(deleting.id)}
        busy={deleteM.isPending}
      />
    </div>
  );
}
