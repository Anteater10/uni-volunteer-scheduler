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
import FormFieldsDrawer from "../../components/admin/FormFieldsDrawer";
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

function TemplateForm({ form, setForm, isCreate, onSubmit, onArchive, onClone, onCancel, onEditFormFields, submitting }) {
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

      {/* Form fields (Phase 22) — edit-only */}
      {!isCreate && onEditFormFields && (
        <div className="pt-2 border-t border-[var(--color-border)]">
          <Button type="button" variant="secondary" onClick={onEditFormFields}>
            Edit form fields
          </Button>
          <p className="text-xs text-[var(--color-fg-muted)] mt-1">
            Custom signup questions volunteers answer for every event created
            from this template.
          </p>
        </div>
      )}

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
        {!isCreate && onClone && (
          <Button
            type="button"
            variant="secondary"
            onClick={onClone}
          >
            Clone
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
  const [formFieldsFor, setFormFieldsFor] = useState(null); // template (with slug + default_form_schema) being edited

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

  const cloneM = useMutation({
    mutationFn: ({ slug, new_slug, new_name }) =>
      api.admin.templates.clone(slug, { new_slug, new_name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminTemplates"] });
      setDrawerTemplate(null);
      toast.success("Template cloned");
    },
    onError: (e) => toast.error(e?.message || "Failed to clone template"),
  });

  function handleClone() {
    if (!drawerTemplate) return;
    const suggested = `${drawerTemplate.slug}-copy`;
    const new_slug = window.prompt(
      "Slug for the cloned template (lowercase, hyphens only):",
      suggested,
    );
    if (!new_slug) return;
    const new_name = window.prompt(
      "Name for the cloned template:",
      `${drawerTemplate.name} (copy)`,
    );
    cloneM.mutate({ slug: drawerTemplate.slug, new_slug, new_name });
  }

  // Phase 22 — default form schema persistence
  const defaultSchemaM = useMutation({
    mutationFn: ({ slug, schema }) =>
      api.admin.templates.setDefaultFormSchema(slug, schema),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminTemplates"] });
      setFormFieldsFor(null);
      toast.success("Form fields saved");
    },
    onError: (e) => toast.error(e?.message || "Failed to save form fields"),
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
          <h1 className="text-5xl font-bold tracking-tight">Templates</h1>
          <p className="text-xl text-[var(--color-fg-muted)] mt-3">
            Module templates define the sessions, capacity, and materials for each SciTrek module.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="px-8 py-4 text-xl font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow"
        >
          + New template
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-4">
        <input
          id="tmpl-search"
          placeholder="Search by name..."
          value={search}
          onChange={handleSearchChange}
          className="flex-1 min-w-[20rem] rounded-xl border border-gray-300 px-5 py-4 text-xl"
        />
        <select
          id="tmpl-type"
          aria-label="Filter by type"
          value={typeFilter}
          onChange={handleTypeFilterChange}
          className="rounded-xl border border-gray-300 px-5 py-4 text-xl bg-white"
        >
          <option value="all">All types</option>
          <option value="module">Module</option>
          <option value="seminar">Seminar</option>
          <option value="orientation">Orientation</option>
        </select>
        <label className="flex items-center gap-2 text-lg" htmlFor="tmpl-archived">
          <input
            id="tmpl-archived"
            type="checkbox"
            checked={showArchived}
            onChange={handleShowArchivedChange}
            className="h-5 w-5"
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
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full text-2xl">
              <thead className="bg-gray-50 text-left text-xl uppercase tracking-wide text-gray-600">
                <tr>
                  <th className="py-5 px-6">Name</th>
                  <th className="py-5 px-6">Type</th>
                  <th className="py-5 px-6">Duration</th>
                  <th className="py-5 px-6">Sessions</th>
                  <th className="py-5 px-6">Capacity</th>
                  {showArchived && <th className="py-5 px-6">Status</th>}
                  <th className="py-5 px-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {pageData.map((t) => {
                  const isArchived = !!t.deleted_at;
                  return (
                    <tr
                      key={t.slug}
                      className={`cursor-pointer hover:bg-gray-50 ${
                        isArchived ? "opacity-60" : ""
                      }`}
                      onClick={() => !isArchived && openEdit(t)}
                    >
                      <td className="py-6 px-6 font-semibold">{t.name}</td>
                      <td className="py-6 px-6">
                        <span
                          className={`inline-flex items-center rounded-full px-3 py-1 text-base font-medium ${
                            TYPE_BADGE[t.type] || "bg-gray-100 text-gray-700"
                          }`}
                        >
                          {capitalize(t.type)}
                        </span>
                      </td>
                      <td className="py-6 px-6 text-gray-800">{t.duration_minutes} min</td>
                      <td className="py-6 px-6 text-gray-800">
                        {t.session_count === 1
                          ? "1 session"
                          : `${t.session_count} sessions`}
                      </td>
                      <td className="py-6 px-6 text-gray-800">{t.default_capacity}</td>
                      {showArchived && (
                        <td className="py-6 px-6">
                          {isArchived ? (
                            <span className="inline-flex items-center rounded-full px-3 py-1 text-base font-medium bg-gray-100 text-gray-600">
                              Archived
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full px-3 py-1 text-base font-medium bg-green-100 text-green-700">
                              Active
                            </span>
                          )}
                        </td>
                      )}
                      <td
                        className="py-6 px-6 text-right space-x-5 whitespace-nowrap"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {isArchived ? (
                          <button
                            type="button"
                            onClick={() => restoreM.mutate(t.slug)}
                            disabled={restoreM.isPending}
                            className="text-blue-600 hover:underline font-medium disabled:opacity-50"
                          >
                            Restore
                          </button>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => openEdit(t)}
                              className="text-blue-600 hover:underline font-medium"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => setArchiveConfirm(t.slug)}
                              className="text-red-600 hover:underline font-medium"
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </td>
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
            onClone={handleClone}
            onCancel={() => setDrawerTemplate(null)}
            onEditFormFields={() => setFormFieldsFor(drawerTemplate)}
            submitting={updateM.isPending}
          />
        )}
      </SideDrawer>

      {/* Phase 22 — default form schema drawer */}
      <FormFieldsDrawer
        open={!!formFieldsFor}
        onClose={() => setFormFieldsFor(null)}
        title={`Form fields — ${formFieldsFor?.name || ""}`}
        schema={formFieldsFor?.default_form_schema || []}
        saving={defaultSchemaM.isPending}
        onSave={(nextSchema) =>
          defaultSchemaM.mutate({
            slug: formFieldsFor.slug,
            schema: nextSchema,
          })
        }
      />

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
