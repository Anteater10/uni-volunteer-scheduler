// src/pages/admin/TemplatesSection.jsx
//
// Phase 17 Plan 02 — Templates CRUD with SideDrawer pattern.
// ADMIN-08..11: list, create, edit (update), archive (soft-delete), restore.
// D-18: plain-English labels. D-19: humanized names. D-52/53: breadcrumbs.

import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../lib/api";
import { useAdminPageTitle } from "./AdminLayout";
import SideDrawer from "../../components/admin/SideDrawer";
import Pagination from "../../components/admin/Pagination";
import {
  Button,
  Modal,
  Input,
  Label,
  EmptyState,
  Skeleton,
} from "../../components/ui";
import { toast } from "../../state/toast";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 10;

const TYPE_OPTIONS = [
  { value: "module", label: "Module" },
  { value: "seminar", label: "Seminar" },
  { value: "orientation", label: "Orientation" },
];

const TYPE_BADGE = {
  seminar: "bg-blue-100 text-blue-800",
  orientation: "bg-green-100 text-green-800",
  module: "bg-gray-100 text-gray-700",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 64);
}

function emptyForm() {
  return {
    name: "",
    slug: "",
    type: "module",
    duration_minutes: 90,
    session_count: 1,
    default_capacity: 30,
    description: "",
    materials: "",
  };
}

function templateToForm(t) {
  return {
    name: t.name || "",
    slug: t.slug || "",
    type: t.type || "module",
    duration_minutes: t.duration_minutes ?? 90,
    session_count: t.session_count ?? 1,
    default_capacity: t.default_capacity ?? 30,
    description: t.description || "",
    materials: Array.isArray(t.materials) ? t.materials.join(", ") : (t.materials || ""),
  };
}

// ---------------------------------------------------------------------------
// TemplateForm — shared create/edit form rendered inside SideDrawer
// ---------------------------------------------------------------------------

function TemplateForm({ form, setForm, isCreate, onSubmit, onArchive, onCancel, submitting }) {
  function handleNameChange(e) {
    const name = e.target.value;
    setForm((prev) => ({
      ...prev,
      name,
      // Auto-generate slug only while creating (don't overwrite read-only slug on edit)
      ...(isCreate ? { slug: slugify(name) } : {}),
    }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit(form);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Template name */}
      <div>
        <Label htmlFor="tf-name">Template name</Label>
        <Input
          id="tf-name"
          value={form.name}
          onChange={handleNameChange}
          required
          placeholder="e.g. DNA Extraction Module"
        />
      </div>

      {/* URL slug */}
      <div>
        <Label htmlFor="tf-slug">URL slug</Label>
        <Input
          id="tf-slug"
          value={form.slug}
          onChange={(e) => isCreate && setForm((p) => ({ ...p, slug: e.target.value }))}
          readOnly={!isCreate}
          required
          placeholder="e.g. dna-extraction-module"
          className={!isCreate ? "opacity-60 cursor-not-allowed" : ""}
        />
        {isCreate && (
          <p className="text-xs text-[var(--color-fg-muted)] mt-1">
            Auto-generated from name. You can edit it.
          </p>
        )}
      </div>

      {/* Type */}
      <div>
        <Label htmlFor="tf-type">Type</Label>
        <select
          id="tf-type"
          value={form.type}
          onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}
          className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
        >
          {TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* Duration */}
      <div>
        <Label htmlFor="tf-dur">Duration (minutes)</Label>
        <Input
          id="tf-dur"
          type="number"
          min="1"
          value={form.duration_minutes}
          onChange={(e) => setForm((p) => ({ ...p, duration_minutes: Number(e.target.value) }))}
          required
        />
      </div>

      {/* Number of sessions */}
      <div>
        <Label htmlFor="tf-sessions">Number of sessions</Label>
        <Input
          id="tf-sessions"
          type="number"
          min="1"
          max="10"
          value={form.session_count}
          onChange={(e) => setForm((p) => ({ ...p, session_count: Number(e.target.value) }))}
          required
        />
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          How many class sessions does this module span?
        </p>
      </div>

      {/* Default capacity */}
      <div>
        <Label htmlFor="tf-cap">Default capacity</Label>
        <Input
          id="tf-cap"
          type="number"
          min="1"
          value={form.default_capacity}
          onChange={(e) => setForm((p) => ({ ...p, default_capacity: Number(e.target.value) }))}
          required
        />
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          Maximum students per session
        </p>
      </div>

      {/* Description */}
      <div>
        <Label htmlFor="tf-desc">Description</Label>
        <textarea
          id="tf-desc"
          value={form.description}
          onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
          className="w-full min-h-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
          placeholder="Optional short description"
        />
      </div>

      {/* Materials */}
      <div>
        <Label htmlFor="tf-mat">Materials</Label>
        <Input
          id="tf-mat"
          value={form.materials}
          onChange={(e) => setForm((p) => ({ ...p, materials: e.target.value }))}
          placeholder="e.g. gloves, test tubes, slides"
        />
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          Comma-separated list of required materials
        </p>
      </div>

      {/* Footer */}
      <div className="flex items-center gap-2 pt-2">
        {!isCreate && (
          <Button
            type="button"
            variant="danger"
            onClick={onArchive}
          >
            Archive
          </Button>
        )}
        <div className="flex-1" />
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting
            ? isCreate
              ? "Creating..."
              : "Saving..."
            : isCreate
            ? "Create template"
            : "Save changes"}
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// TemplatesSection
// ---------------------------------------------------------------------------

export default function TemplatesSection() {
  useAdminPageTitle("Templates");
  const qc = useQueryClient();

  // --- UI state ---
  const [drawerTemplate, setDrawerTemplate] = useState(null); // template being edited
  const [createOpen, setCreateOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [archiveConfirm, setArchiveConfirm] = useState(null); // slug or null

  // --- Form state for create/edit ---
  const [form, setForm] = useState(emptyForm());

  // --- Query ---
  const listQ = useQuery({
    queryKey: ["adminTemplates", { include_archived: showArchived }],
    queryFn: () =>
      api.admin.templates.list(showArchived ? { include_archived: true } : undefined),
  });

  // --- Mutations ---
  const createM = useMutation({
    mutationFn: (payload) => api.admin.templates.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminTemplates"] });
      setCreateOpen(false);
      setForm(emptyForm());
      toast.success("Template created");
    },
    onError: (e) => toast.error(e?.message || "Failed to create template"),
  });

  const updateM = useMutation({
    mutationFn: ({ slug, payload }) => api.admin.templates.update(slug, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminTemplates"] });
      setDrawerTemplate(null);
      toast.success("Template updated");
    },
    onError: (e) => toast.error(e?.message || "Failed to update template"),
  });

  const archiveM = useMutation({
    mutationFn: (slug) => api.admin.templates.delete(slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminTemplates"] });
      setArchiveConfirm(null);
      setDrawerTemplate(null);
      toast.success("Template archived");
    },
    onError: (e) => toast.error(e?.message || "Failed to archive template"),
  });

  const restoreM = useMutation({
    mutationFn: (slug) => api.admin.templates.restore(slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminTemplates"] });
      toast.success("Template restored");
    },
    onError: (e) => toast.error(e?.message || "Failed to restore template"),
  });

  // --- Client-side filtering + pagination ---
  const filtered = useMemo(() => {
    let result = listQ.data || [];
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((t) => t.name.toLowerCase().includes(q));
    }
    if (typeFilter !== "all") {
      result = result.filter((t) => t.type === typeFilter);
    }
    return result;
  }, [listQ.data, search, typeFilter]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageData = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // --- Handlers ---
  function openCreate() {
    setForm(emptyForm());
    setCreateOpen(true);
  }

  function openEdit(t) {
    setForm(templateToForm(t));
    setDrawerTemplate(t);
  }

  function handleCreate(formData) {
    createM.mutate({
      slug: formData.slug,
      name: formData.name,
      type: formData.type,
      duration_minutes: Number(formData.duration_minutes),
      session_count: Number(formData.session_count),
      default_capacity: Number(formData.default_capacity),
      description: formData.description || null,
      materials: formData.materials
        ? formData.materials.split(",").map((s) => s.trim()).filter(Boolean)
        : [],
    });
  }

  function handleUpdate(formData) {
    if (!drawerTemplate) return;
    updateM.mutate({
      slug: drawerTemplate.slug,
      payload: {
        name: formData.name,
        type: formData.type,
        duration_minutes: Number(formData.duration_minutes),
        session_count: Number(formData.session_count),
        default_capacity: Number(formData.default_capacity),
        description: formData.description || null,
        materials: formData.materials
          ? formData.materials.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
      },
    });
  }

  // Reset to page 1 when filters change
  function handleSearchChange(e) {
    setSearch(e.target.value);
    setPage(1);
  }

  function handleTypeFilterChange(e) {
    setTypeFilter(e.target.value);
    setPage(1);
  }

  function handleShowArchivedChange(e) {
    setShowArchived(e.target.checked);
    setPage(1);
  }

  // Name of template being confirmed for archive
  const archiveTargetName = archiveConfirm
    ? (listQ.data || []).find((t) => t.slug === archiveConfirm)?.name || archiveConfirm
    : null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Templates</h1>
          <p className="text-[var(--color-fg-muted)]">
            Module templates define the sessions, capacity, and materials for each SciTrek module.
          </p>
        </div>
        <Button onClick={openCreate}>New template</Button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[12rem]">
          <Label htmlFor="tmpl-search" className="sr-only">
            Search by name
          </Label>
          <Input
            id="tmpl-search"
            placeholder="Search by name..."
            value={search}
            onChange={handleSearchChange}
          />
        </div>
        <div>
          <Label htmlFor="tmpl-type" className="sr-only">
            Filter by type
          </Label>
          <select
            id="tmpl-type"
            aria-label="Filter by type"
            value={typeFilter}
            onChange={handleTypeFilterChange}
            className="min-h-11 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-sm"
          >
            <option value="all">All types</option>
            <option value="module">Module</option>
            <option value="seminar">Seminar</option>
            <option value="orientation">Orientation</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm" htmlFor="tmpl-archived">
          <input
            id="tmpl-archived"
            type="checkbox"
            checked={showArchived}
            onChange={handleShowArchivedChange}
          />
          Show archived
        </label>
      </div>

      {/* Body: loading / error / empty / table */}
      {listQ.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : listQ.error ? (
        <EmptyState
          title="Couldn't load templates"
          body={listQ.error.message}
          action={<Button onClick={() => listQ.refetch()}>Retry</Button>}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No templates yet"
          body="Create a module template to get started."
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
            <table className="w-full text-left text-sm">
              <thead className="bg-[var(--color-bg-muted)] text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">
                <tr>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Duration</th>
                  <th className="px-3 py-2">Sessions</th>
                  <th className="px-3 py-2">Capacity</th>
                  {showArchived && <th className="px-3 py-2">Status</th>}
                  {showArchived && <th className="px-3 py-2" />}
                </tr>
              </thead>
              <tbody>
                {pageData.map((t) => {
                  const isArchived = !!t.deleted_at;
                  return (
                    <tr
                      key={t.slug}
                      className={`border-t border-[var(--color-border)] cursor-pointer hover:bg-[var(--color-bg-muted)] ${
                        isArchived ? "opacity-60" : ""
                      }`}
                      onClick={() => !isArchived && openEdit(t)}
                    >
                      <td className="px-3 py-2 font-medium">{t.name}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            TYPE_BADGE[t.type] || "bg-gray-100 text-gray-700"
                          }`}
                        >
                          {capitalize(t.type)}
                        </span>
                      </td>
                      <td className="px-3 py-2">{t.duration_minutes} min</td>
                      <td className="px-3 py-2">
                        {t.session_count === 1
                          ? "1 session"
                          : `${t.session_count} sessions`}
                      </td>
                      <td className="px-3 py-2">{t.default_capacity}</td>
                      {showArchived && (
                        <td className="px-3 py-2">
                          {isArchived ? (
                            <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600">
                              Archived
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700">
                              Active
                            </span>
                          )}
                        </td>
                      )}
                      {showArchived && (
                        <td
                          className="px-3 py-2 text-right"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {isArchived && (
                            <Button
                              variant="secondary"
                              onClick={() => restoreM.mutate(t.slug)}
                              disabled={restoreM.isPending}
                            >
                              Restore
                            </Button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
          )}
        </>
      )}

      {/* Create SideDrawer */}
      <SideDrawer
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New template"
      >
        <TemplateForm
          form={form}
          setForm={setForm}
          isCreate
          onSubmit={handleCreate}
          onCancel={() => setCreateOpen(false)}
          submitting={createM.isPending}
        />
      </SideDrawer>

      {/* Edit SideDrawer */}
      <SideDrawer
        open={!!drawerTemplate}
        onClose={() => setDrawerTemplate(null)}
        title="Edit template"
      >
        {drawerTemplate && (
          <TemplateForm
            form={form}
            setForm={setForm}
            isCreate={false}
            onSubmit={handleUpdate}
            onArchive={() => setArchiveConfirm(drawerTemplate.slug)}
            onCancel={() => setDrawerTemplate(null)}
            submitting={updateM.isPending}
          />
        )}
      </SideDrawer>

      {/* Archive confirmation Modal */}
      <Modal
        open={!!archiveConfirm}
        onClose={() => setArchiveConfirm(null)}
        title="Archive this template?"
      >
        <p className="text-sm">
          Archiving removes <strong>{archiveTargetName}</strong> from the active list.
          You can restore it later.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setArchiveConfirm(null)}>
            Keep it
          </Button>
          <Button
            variant="danger"
            disabled={archiveM.isPending}
            onClick={() => archiveM.mutate(archiveConfirm)}
          >
            {archiveM.isPending ? "Archiving..." : "Yes, archive"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
