// AdminTemplatesPage.jsx -- TODO(brand) TODO(copy)
import React, { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { PageHeader, Card, Button, Skeleton } from "../components/ui";

function TemplateRow({ tpl, onEdit, onDelete }) {
  return (
    <tr className="border-b border-[var(--color-border)]">
      <td className="px-3 py-2 font-mono text-sm">{tpl.slug}</td>
      <td className="px-3 py-2">{tpl.name}</td>
      <td className="px-3 py-2 text-center">{tpl.default_capacity}</td>
      <td className="px-3 py-2 text-center">{tpl.duration_minutes}m</td>
      <td className="px-3 py-2 text-sm text-[var(--color-fg-muted)]">
        {(tpl.prereq_slugs || []).join(", ") || "None"}
      </td>
      <td className="px-3 py-2 space-x-2 text-right">
        <Button size="sm" variant="outline" onClick={() => onEdit(tpl)}>
          Edit
        </Button>
        <Button size="sm" variant="destructive" onClick={() => onDelete(tpl.slug)}>
          Delete
        </Button>
      </td>
    </tr>
  );
}

function EditForm({ initial, onSave, onCancel }) {
  const isNew = !initial;
  const [form, setForm] = useState(
    initial || {
      slug: "",
      name: "",
      default_capacity: 20,
      duration_minutes: 90,
      prereq_slugs: [],
      materials: [],
      description: "",
    }
  );

  const handleChange = (field, value) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  return (
    <Card className="space-y-3">
      {/* TODO(copy) */}
      <h3 className="font-semibold">
        {isNew ? "Create Template" : `Edit: ${form.slug}`}
      </h3>
      {isNew && (
        <label className="block">
          <span className="text-sm">Slug</span>
          <input
            className="block w-full mt-1 rounded border px-2 py-1 text-sm"
            value={form.slug}
            onChange={(e) => handleChange("slug", e.target.value)}
          />
        </label>
      )}
      <label className="block">
        <span className="text-sm">Name</span>
        <input
          className="block w-full mt-1 rounded border px-2 py-1 text-sm"
          value={form.name}
          onChange={(e) => handleChange("name", e.target.value)}
        />
      </label>
      <div className="flex gap-4">
        <label className="block flex-1">
          <span className="text-sm">Capacity</span>
          <input
            type="number"
            className="block w-full mt-1 rounded border px-2 py-1 text-sm"
            value={form.default_capacity}
            onChange={(e) =>
              handleChange("default_capacity", Number(e.target.value))
            }
          />
        </label>
        <label className="block flex-1">
          <span className="text-sm">Duration (min)</span>
          <input
            type="number"
            className="block w-full mt-1 rounded border px-2 py-1 text-sm"
            value={form.duration_minutes}
            onChange={(e) =>
              handleChange("duration_minutes", Number(e.target.value))
            }
          />
        </label>
      </div>
      <label className="block">
        <span className="text-sm">Description</span>
        <textarea
          className="block w-full mt-1 rounded border px-2 py-1 text-sm"
          rows={2}
          value={form.description || ""}
          onChange={(e) => handleChange("description", e.target.value)}
        />
      </label>
      <div className="flex gap-2">
        <Button onClick={() => onSave(form)}>{isNew ? "Create" : "Save"}</Button>
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </Card>
  );
}

export default function AdminTemplatesPage() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | template object
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const fetchTemplates = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getModuleTemplates();
      setTemplates(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleSave = async (form) => {
    try {
      setError(null);
      if (editing) {
        const { slug, ...rest } = form;
        await api.updateModuleTemplate(slug, rest);
      } else {
        await api.createModuleTemplate(form);
      }
      setEditing(null);
      setCreating(false);
      fetchTemplates();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (slug) => {
    if (!window.confirm(`Delete template "${slug}"?`)) return;
    try {
      setError(null);
      await api.deleteModuleTemplate(slug);
      fetchTemplates();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="Module Templates" />

      {error && (
        <div className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {(editing || creating) && (
        <EditForm
          initial={editing}
          onSave={handleSave}
          onCancel={() => {
            setEditing(null);
            setCreating(false);
          }}
        />
      )}

      {!editing && !creating && (
        <Button onClick={() => setCreating(true)}>+ Create Template</Button>
      )}

      {loading ? (
        <Skeleton className="h-40" />
      ) : (
        <Card className="overflow-x-auto !p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-muted)]">
                <th className="px-3 py-2 text-left">Slug</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-center">Capacity</th>
                <th className="px-3 py-2 text-center">Duration</th>
                <th className="px-3 py-2 text-left">Prerequisites</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((tpl) => (
                <TemplateRow
                  key={tpl.slug}
                  tpl={tpl}
                  onEdit={setEditing}
                  onDelete={handleDelete}
                />
              ))}
              {templates.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-[var(--color-fg-muted)]">
                    No templates yet. Create one to get started. {/* TODO(copy) */}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
