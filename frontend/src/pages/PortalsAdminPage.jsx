// src/pages/PortalsAdminPage.jsx
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

export default function PortalsAdminPage() {
  const [portals, setPortals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", slug: "", description: "" });
  const [pendingDelete, setPendingDelete] = useState(null);

  async function load() {
    setErr("");
    setLoading(true);
    try {
      const data = await api.listPortals();
      setPortals(data || []);
    } catch (e) {
      setErr(e?.message || "Failed to load portals");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createPortal(e) {
    e.preventDefault();
    setErr("");
    setCreating(true);
    try {
      await api.createPortal({
        name: form.name.trim(),
        slug: form.slug.trim(),
        description: form.description?.trim() || null,
      });
      setForm({ name: "", slug: "", description: "" });
      // TODO(copy)
      toast.success("Portal created.");
      load();
    } catch (e2) {
      setErr(e2?.message || "Failed to create portal");
    } finally {
      setCreating(false);
    }
  }

  function doDelete() {
    if (!pendingDelete) return;
    setPendingDelete(null);
    // TODO(copy): delete portal endpoint not wired
    toast.info("Delete portal: backend endpoint not yet wired.");
  }

  return (
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="Portals" />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : err ? (
        <EmptyState
          /* TODO(copy) */
          title="Couldn't load portals"
          /* TODO(copy) */
          body={err}
          action={
            <Button onClick={load}>
              {/* TODO(copy) */}
              Retry
            </Button>
          }
        />
      ) : portals.length === 0 ? (
        <EmptyState
          /* TODO(copy) */
          title="No portals yet"
        />
      ) : (
        <div className="space-y-3">
          {portals.map((p) => (
            <Card key={p.id}>
              <h3 className="font-semibold">{p.name}</h3>
              <p className="text-sm text-[var(--color-fg-muted)]">/{p.slug}</p>
              {p.description && (
                <p className="text-sm mt-1">{p.description}</p>
              )}
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" as={Link} to={`/portals/${p.slug}`}>
                  {/* TODO(copy) */}
                  Open public
                </Button>
                <Button variant="danger" onClick={() => setPendingDelete(p)}>
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
          Create portal
        </h2>
        <Card>
          <form onSubmit={createPortal} className="space-y-3">
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="np-name">Name</Label>
              <Input
                id="np-name"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="np-slug">Slug</Label>
              <Input
                id="np-slug"
                value={form.slug}
                onChange={(e) => setForm((p) => ({ ...p, slug: e.target.value }))}
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="np-desc">Description</Label>
              <Input
                id="np-desc"
                value={form.description}
                onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              />
            </div>
            <FieldError>{err}</FieldError>
            <div className="flex justify-end">
              <Button type="submit" disabled={creating}>
                {/* TODO(copy) */}
                {creating ? "Creating..." : "Create portal"}
              </Button>
            </div>
          </form>
        </Card>
      </section>

      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        /* TODO(copy) */
        title="Delete portal"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Delete portal "{pendingDelete?.name}"?
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setPendingDelete(null)}>
            {/* TODO(copy) */}
            Keep
          </Button>
          <Button variant="danger" onClick={doDelete}>
            {/* TODO(copy) */}
            Delete portal
          </Button>
        </div>
      </Modal>
    </div>
  );
}
