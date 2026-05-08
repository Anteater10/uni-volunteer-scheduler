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
import { useAdminPageTitle } from "./admin/AdminLayout";

export default function PortalsAdminPage() {
  useAdminPageTitle("Portals");
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
    toast.info(
      "Deleting portals is not available yet. Contact the developer to remove a portal.",
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Portals"
        subtitle="Portals are the public-facing landing pages volunteers use to see events."
      />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : err ? (
        <EmptyState
          title="Couldn't load portals"
          body={err}
          action={<Button onClick={load}>Try again</Button>}
        />
      ) : portals.length === 0 ? (
        <EmptyState
          title="No portals yet"
          body="Create your first portal below to give volunteers a public landing page."
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
                  View public page
                </Button>
                <Button variant="danger" onClick={() => setPendingDelete(p)}>
                  Delete portal
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <section>
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mt-4 mb-2">
          Create a new portal
        </h2>
        <Card>
          <form onSubmit={createPortal} className="space-y-3">
            <div>
              <Label htmlFor="np-name">Portal name</Label>
              <Input
                id="np-name"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="np-slug">URL slug (short name used in the link)</Label>
              <Input
                id="np-slug"
                value={form.slug}
                onChange={(e) => setForm((p) => ({ ...p, slug: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="np-desc">Short description (optional)</Label>
              <Input
                id="np-desc"
                value={form.description}
                onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              />
            </div>
            <FieldError>{err}</FieldError>
            <div className="flex justify-end">
              <Button type="submit" disabled={creating}>
                {creating ? "Creating…" : "Create portal"}
              </Button>
            </div>
          </form>
        </Card>
      </section>

      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="Delete portal"
      >
        <p className="text-sm">
          Delete the portal "{pendingDelete?.name}"? Volunteers will no
          longer be able to use its public link.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setPendingDelete(null)}>
            Keep portal
          </Button>
          <Button variant="danger" onClick={doDelete}>
            Delete portal
          </Button>
        </div>
      </Modal>
    </div>
  );
}
