// src/pages/admin/TemplatesSection.jsx
import React, { useState, useCallback } from "react";
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

function InlineEditCell({ value, onSave, type = "text" }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  function handleSave() {
    setEditing(false);
    if (draft !== value) onSave(draft);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter") handleSave();
    if (e.key === "Escape") {
      setDraft(value);
      setEditing(false);
    }
  }

  if (editing) {
    return (
      <input
        type={type}
        className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
        value={draft}
        onChange={(e) => setDraft(type === "number" ? Number(e.target.value) : e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        autoFocus
      />
    );
  }

  return (
    <span
      className="cursor-pointer hover:bg-[var(--color-bg-active,#f3f4f6)] px-1 py-0.5 rounded inline-block"
      onClick={() => {
        setDraft(value);
        setEditing(true);
      }}
    >
      {String(value ?? "--")}
    </span>
  );
}

export default function TemplatesSection() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [showBulkDelete, setShowBulkDelete] = useState(false);
  const [newTemplate, setNewTemplate] = useState({
    slug: "",
    name: "",
    default_capacity: 20,
    duration_minutes: 90,
    prereq_slugs: "",
    materials: "",
    description: "",
  });

  const templatesQ = useQuery({
    queryKey: ["adminTemplates"],
    queryFn: () => api.admin.templates.list(),
  });

  const updateMut = useMutation({
    mutationFn: ({ slug, data }) => api.admin.templates.update(slug, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adminTemplates"] });
      toast.success("Template updated.");
    },
    onError: (err) => toast.error(err?.message || "Update failed"),
  });

  const createMut = useMutation({
    mutationFn: (payload) => api.admin.templates.create(payload),
    onSuccess: () => {
      setShowCreate(false);
      setNewTemplate({
        slug: "", name: "", default_capacity: 20, duration_minutes: 90,
        prereq_slugs: "", materials: "", description: "",
      });
      queryClient.invalidateQueries({ queryKey: ["adminTemplates"] });
      toast.success("Template created.");
    },
    onError: (err) => toast.error(err?.message || "Create failed"),
  });

  const bulkDeleteMut = useMutation({
    mutationFn: (slugs) => api.admin.templates.bulkDelete(slugs),
    onSuccess: () => {
      setSelected(new Set());
      setShowBulkDelete(false);
      queryClient.invalidateQueries({ queryKey: ["adminTemplates"] });
      toast.success("Templates deleted.");
    },
    onError: (err) => toast.error(err?.message || "Delete failed"),
  });

  const templates = templatesQ.data || [];

  const toggleSelect = useCallback((slug) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selected.size === templates.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(templates.map((t) => t.slug)));
    }
  }, [templates, selected.size]);

  function handleInlineUpdate(slug, field, value) {
    const data = {};
    if (field === "prereq_slugs") {
      data[field] = value.split(",").map((s) => s.trim()).filter(Boolean);
    } else {
      data[field] = value;
    }
    updateMut.mutate({ slug, data });
  }

  function handleCreate(e) {
    e.preventDefault();
    createMut.mutate({
      slug: newTemplate.slug,
      name: newTemplate.name,
      default_capacity: Number(newTemplate.default_capacity),
      duration_minutes: Number(newTemplate.duration_minutes),
      prereq_slugs: newTemplate.prereq_slugs.split(",").map((s) => s.trim()).filter(Boolean),
      materials: newTemplate.materials.split(",").map((s) => s.trim()).filter(Boolean),
      description: newTemplate.description || null,
    });
  }

  return (
    <div className="space-y-4">
      {/* Action bar */}
      <div className="flex flex-wrap gap-3">
        <Button onClick={() => setShowCreate(true)}>
          {/* TODO(copy) */}
          Add Template
        </Button>
        {selected.size > 0 && (
          <Button variant="danger" onClick={() => setShowBulkDelete(true)}>
            Delete Selected ({selected.size})
          </Button>
        )}
      </div>

      {templatesQ.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : templatesQ.error ? (
        <EmptyState
          title="Couldn't load templates"
          body={templatesQ.error.message}
          action={<Button onClick={() => templatesQ.refetch()}>Retry</Button>}
        />
      ) : templates.length === 0 ? (
        <EmptyState title="No templates" body="Create a module template to get started." />
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <p className="text-xs text-[var(--color-fg-muted)] mb-1">
              {/* TODO(copy) */}
              Click a cell to edit inline. Tab/Enter saves, Escape cancels.
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left">
                  <th className="py-2 pr-3">
                    <input
                      type="checkbox"
                      checked={selected.size === templates.length && templates.length > 0}
                      onChange={toggleAll}
                    />
                  </th>
                  <th className="py-2 pr-3 font-medium">Slug</th>
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Capacity</th>
                  <th className="py-2 pr-3 font-medium">Duration (min)</th>
                  <th className="py-2 pr-3 font-medium">Prereqs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {templates.map((t) => (
                  <tr key={t.slug}>
                    <td className="py-2 pr-3">
                      <input
                        type="checkbox"
                        checked={selected.has(t.slug)}
                        onChange={() => toggleSelect(t.slug)}
                      />
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{t.slug}</td>
                    <td className="py-2 pr-3">
                      <InlineEditCell
                        value={t.name}
                        onSave={(v) => handleInlineUpdate(t.slug, "name", v)}
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <InlineEditCell
                        value={t.default_capacity}
                        type="number"
                        onSave={(v) => handleInlineUpdate(t.slug, "default_capacity", Number(v))}
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <InlineEditCell
                        value={t.duration_minutes}
                        type="number"
                        onSave={(v) => handleInlineUpdate(t.slug, "duration_minutes", Number(v))}
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <InlineEditCell
                        value={(t.prereq_slugs || []).join(", ")}
                        onSave={(v) => handleInlineUpdate(t.slug, "prereq_slugs", v)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: horizontal scroll hint */}
          <div className="md:hidden">
            <p className="text-xs text-[var(--color-fg-muted)] mb-1">
              Open on desktop for inline editing
            </p>
            <div className="space-y-3">
              {templates.map((t) => (
                <Card key={t.slug}>
                  <div className="flex items-baseline gap-2">
                    <input
                      type="checkbox"
                      checked={selected.has(t.slug)}
                      onChange={() => toggleSelect(t.slug)}
                    />
                    <span className="font-mono text-xs">{t.slug}</span>
                    <span className="font-medium">{t.name}</span>
                  </div>
                  <p className="text-sm text-[var(--color-fg-muted)] mt-1">
                    Capacity: {t.default_capacity} | Duration: {t.duration_minutes}min
                  </p>
                  {t.prereq_slugs?.length > 0 && (
                    <p className="text-xs text-[var(--color-fg-muted)]">
                      Prereqs: {t.prereq_slugs.join(", ")}
                    </p>
                  )}
                </Card>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Create Modal */}
      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Add Template"
      >
        <form onSubmit={handleCreate} className="space-y-3">
          <div>
            <Label htmlFor="ct-slug">Slug</Label>
            <Input
              id="ct-slug"
              value={newTemplate.slug}
              onChange={(e) => setNewTemplate((p) => ({ ...p, slug: e.target.value }))}
              placeholder="e.g. orientation-101"
            />
          </div>
          <div>
            <Label htmlFor="ct-name">Name</Label>
            <Input
              id="ct-name"
              value={newTemplate.name}
              onChange={(e) => setNewTemplate((p) => ({ ...p, name: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="ct-cap">Capacity</Label>
              <Input
                id="ct-cap"
                type="number"
                value={newTemplate.default_capacity}
                onChange={(e) => setNewTemplate((p) => ({ ...p, default_capacity: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="ct-dur">Duration (min)</Label>
              <Input
                id="ct-dur"
                type="number"
                value={newTemplate.duration_minutes}
                onChange={(e) => setNewTemplate((p) => ({ ...p, duration_minutes: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <Label htmlFor="ct-prereqs">Prereq Slugs (comma-separated)</Label>
            <Input
              id="ct-prereqs"
              value={newTemplate.prereq_slugs}
              onChange={(e) => setNewTemplate((p) => ({ ...p, prereq_slugs: e.target.value }))}
              placeholder="slug-1, slug-2"
            />
          </div>
          <div>
            <Label htmlFor="ct-mat">Materials (comma-separated)</Label>
            <Input
              id="ct-mat"
              value={newTemplate.materials}
              onChange={(e) => setNewTemplate((p) => ({ ...p, materials: e.target.value }))}
              placeholder="item-1, item-2"
            />
          </div>
          <div>
            <Label htmlFor="ct-desc">Description</Label>
            <textarea
              id="ct-desc"
              className="w-full min-h-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              value={newTemplate.description}
              onChange={(e) => setNewTemplate((p) => ({ ...p, description: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" disabled={!newTemplate.slug || !newTemplate.name || createMut.isPending}>
              {createMut.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Bulk Delete Confirm */}
      <Modal
        open={showBulkDelete}
        onClose={() => setShowBulkDelete(false)}
        title="Delete Templates"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Delete {selected.size} template{selected.size !== 1 ? "s" : ""}? This cannot be undone.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setShowBulkDelete(false)}>Cancel</Button>
          <Button
            variant="danger"
            disabled={bulkDeleteMut.isPending}
            onClick={() => bulkDeleteMut.mutate([...selected])}
          >
            {bulkDeleteMut.isPending ? "Deleting..." : `Delete ${selected.size}`}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
