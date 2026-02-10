// src/pages/PortalsAdminPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";

export default function PortalsAdminPage() {
  const [portals, setPortals] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedPortalSlug, setSelectedPortalSlug] = useState("");
  const [selectedPortalDetail, setSelectedPortalDetail] = useState(null);

  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [err, setErr] = useState("");

  // Create portal form
  const [createForm, setCreateForm] = useState({
    name: "",
    description: "",
    visibility: "public",
  });
  const [creating, setCreating] = useState(false);

  // Attach flow
  const [attachEventId, setAttachEventId] = useState("");
  const [attachLoading, setAttachLoading] = useState(false);

  async function loadAll() {
    setErr("");
    setLoading(true);
    try {
      const [p, e] = await Promise.all([api.listPortals(), api.listEvents()]);
      setPortals(p || []);
      setEvents(e || []);
    } catch (e2) {
      setErr(e2?.message || "Failed to load portals/events");
    } finally {
      setLoading(false);
    }
  }

  async function loadPortalDetail(slug) {
    if (!slug) return;
    setErr("");
    setDetailLoading(true);
    try {
      const d = await api.getPortalBySlug(slug); // returns {id, name, slug, description, visibility, events: [...]}
      setSelectedPortalDetail(d);
    } catch (e) {
      setErr(e?.message || "Failed to load portal detail");
      setSelectedPortalDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (selectedPortalSlug) loadPortalDetail(selectedPortalSlug);
  }, [selectedPortalSlug]);

  const selectedPortal = useMemo(() => {
    return portals.find((p) => p.slug === selectedPortalSlug) || null;
  }, [portals, selectedPortalSlug]);

  const attachedEventIds = useMemo(() => {
    const ids = new Set((selectedPortalDetail?.events || []).map((e) => String(e.id)));
    return ids;
  }, [selectedPortalDetail]);

  const attachableEvents = useMemo(() => {
    return (events || []).filter((e) => !attachedEventIds.has(String(e.id)));
  }, [events, attachedEventIds]);

  async function createPortal(e) {
    e.preventDefault();
    setErr("");
    if (!createForm.name.trim()) {
      setErr("Portal name is required.");
      return;
    }

    setCreating(true);
    try {
      await api.createPortal({
        name: createForm.name.trim(),
        description: createForm.description?.trim() || null,
        visibility: createForm.visibility || "public",
      });

      setCreateForm({ name: "", description: "", visibility: "public" });
      await loadAll();
    } catch (e2) {
      setErr(e2?.message || "Failed to create portal");
    } finally {
      setCreating(false);
    }
  }

  async function attachSelectedEvent() {
    if (!selectedPortalDetail?.id) {
      setErr("Select a portal first.");
      return;
    }
    if (!attachEventId) {
      setErr("Select an event to attach.");
      return;
    }

    setErr("");
    setAttachLoading(true);
    try {
      await api.attachEventToPortal(selectedPortalDetail.id, attachEventId);
      setAttachEventId("");
      await loadPortalDetail(selectedPortalDetail.slug);
    } catch (e) {
      setErr(e?.message || "Failed to attach event");
    } finally {
      setAttachLoading(false);
    }
  }

  async function detachEvent(eventId) {
    if (!selectedPortalDetail?.id) return;
    setErr("");
    try {
      await api.detachEventFromPortal(selectedPortalDetail.id, eventId);
      await loadPortalDetail(selectedPortalDetail.slug);
    } catch (e) {
      setErr(e?.message || "Failed to detach event");
    }
  }

  return (
    <div style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>Portals (Admin)</h1>
      <p style={{ marginTop: 0, opacity: 0.8 }}>
        Create portals + attach/detach events. (Backend: <code>/portals</code>)
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

      <div style={{ display: "grid", gap: 18, gridTemplateColumns: "1fr 1fr" }}>
        <section>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>Create portal</h2>
          <form onSubmit={createPortal} style={{ display: "grid", gap: 10 }}>
            <label style={{ display: "grid", gap: 6 }}>
              <span>Name</span>
              <input
                value={createForm.name}
                onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="SciTrek Volunteers"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Description</span>
              <textarea
                value={createForm.description}
                onChange={(e) => setCreateForm((p) => ({ ...p, description: e.target.value }))}
                rows={3}
                placeholder="Optional description"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Visibility</span>
              <select
                value={createForm.visibility}
                onChange={(e) => setCreateForm((p) => ({ ...p, visibility: e.target.value }))}
              >
                <option value="public">public</option>
                <option value="private">private</option>
              </select>
            </label>

            <div style={{ display: "flex", gap: 10 }}>
              <button type="submit" disabled={creating}>
                {creating ? "Creating..." : "Create portal"}
              </button>
              <button type="button" onClick={loadAll} disabled={loading}>
                Refresh
              </button>
            </div>
          </form>
        </section>

        <section>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>Select portal</h2>
          {loading ? (
            <div>Loading portals…</div>
          ) : (
            <select
              value={selectedPortalSlug}
              onChange={(e) => setSelectedPortalSlug(e.target.value)}
              style={{ width: "100%" }}
            >
              <option value="">— choose a portal —</option>
              {portals.map((p) => (
                <option key={p.id} value={p.slug}>
                  {p.slug} — {p.name}
                </option>
              ))}
            </select>
          )}

          <div style={{ marginTop: 12, opacity: 0.85 }}>
            {selectedPortal ? (
              <>
                <div>
                  <strong>Name:</strong> {selectedPortal.name}
                </div>
                <div>
                  <strong>Slug:</strong> <code>{selectedPortal.slug}</code>
                </div>
              </>
            ) : (
              <div>Select a portal to manage event attachments.</div>
            )}
          </div>
        </section>
      </div>

      <hr style={{ margin: "18px 0", opacity: 0.2 }} />

      <section>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Attach / detach events</h2>

        {!selectedPortalSlug ? (
          <div style={{ opacity: 0.8 }}>Pick a portal first.</div>
        ) : detailLoading ? (
          <div>Loading portal detail…</div>
        ) : !selectedPortalDetail ? (
          <div style={{ opacity: 0.8 }}>No portal detail loaded.</div>
        ) : (
          <>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select
                value={attachEventId}
                onChange={(e) => setAttachEventId(e.target.value)}
                style={{ minWidth: 320 }}
              >
                <option value="">— select event to attach —</option>
                {attachableEvents.map((ev) => (
                  <option key={ev.id} value={ev.id}>
                    {ev.title} ({String(ev.id).slice(0, 8)}…)
                  </option>
                ))}
              </select>
              <button onClick={attachSelectedEvent} disabled={attachLoading}>
                {attachLoading ? "Attaching..." : "Attach"}
              </button>
            </div>

            <div style={{ marginTop: 14 }}>
              <h3 style={{ fontSize: 16, marginBottom: 8 }}>Attached events</h3>
              {selectedPortalDetail.events?.length ? (
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ textAlign: "left" }}>
                        <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Title</th>
                        <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Event ID</th>
                        <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedPortalDetail.events.map((ev) => (
                        <tr key={ev.id}>
                          <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                            {ev.title}
                          </td>
                          <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                            <code style={{ fontSize: 12 }}>{ev.id}</code>
                          </td>
                          <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                            <button onClick={() => detachEvent(ev.id)} type="button">
                              Detach
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ opacity: 0.8 }}>No events attached yet.</div>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
