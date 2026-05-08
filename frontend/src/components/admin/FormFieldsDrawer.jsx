// src/components/admin/FormFieldsDrawer.jsx
//
// Phase 22 — reusable form-schema CRUD drawer.
// Used by:
//  - TemplatesSection (bound to template.default_form_schema)
//  - AdminEventPage (bound to event.form_schema effective)
//
// Keeps the whole schema in local state until "Save" — parent provides
// onSave(nextSchema) to persist.

import React, { useEffect, useMemo, useState } from "react";
import SideDrawer from "./SideDrawer";
import { Button, Modal, Input, Label, EmptyState } from "../ui";

const FIELD_TYPES = [
  { value: "text", label: "Short text" },
  { value: "textarea", label: "Long text" },
  { value: "select", label: "Dropdown (single choice)" },
  { value: "radio", label: "Radio (single choice)" },
  { value: "checkbox", label: "Checkboxes (multi)" },
  { value: "phone", label: "Phone number" },
  { value: "email", label: "Email" },
];

const OPTION_TYPES = new Set(["select", "radio", "checkbox"]);

function slugify(label) {
  return (label || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
}

function emptyField() {
  return {
    id: "",
    label: "",
    type: "text",
    required: false,
    help_text: "",
    options: "",
    order: 0,
  };
}

function fieldToForm(field) {
  return {
    id: field.id || "",
    label: field.label || "",
    type: field.type || "text",
    required: !!field.required,
    help_text: field.help_text || "",
    options: Array.isArray(field.options) ? field.options.join(", ") : "",
    order: field.order || 0,
  };
}

function formToField(form) {
  const out = {
    id: form.id.trim(),
    label: form.label.trim(),
    type: form.type,
    required: !!form.required,
    order: Number(form.order) || 0,
  };
  if (form.help_text && form.help_text.trim()) out.help_text = form.help_text.trim();
  if (OPTION_TYPES.has(form.type)) {
    out.options = form.options
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  return out;
}

function FieldEditor({ value, onChange, onSubmit, onCancel, isEdit }) {
  function change(key, val) {
    onChange({ ...value, [key]: val });
  }
  function handleLabel(e) {
    const label = e.target.value;
    onChange({
      ...value,
      label,
      // Auto-generate id from label only while creating; keep id stable on edit.
      ...(isEdit ? {} : { id: slugify(label) }),
    });
  }
  const needsOptions = OPTION_TYPES.has(value.type);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="space-y-3"
    >
      <div>
        <Label htmlFor="ff-label">Question / label</Label>
        <Input
          id="ff-label"
          value={value.label}
          onChange={handleLabel}
          required
          placeholder="e.g. T-shirt size"
        />
      </div>
      <div>
        <Label htmlFor="ff-id">Field ID</Label>
        <Input
          id="ff-id"
          value={value.id}
          onChange={(e) =>
            !isEdit && change("id", slugify(e.target.value))
          }
          readOnly={isEdit}
          required
          className={isEdit ? "opacity-60 cursor-not-allowed" : ""}
        />
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          Lowercase slug used in CSV exports. Stable across schema edits.
        </p>
      </div>
      <div>
        <Label htmlFor="ff-type">Type</Label>
        <select
          id="ff-type"
          value={value.type}
          onChange={(e) => change("type", e.target.value)}
          className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
        >
          {FIELD_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
      {needsOptions && (
        <div>
          <Label htmlFor="ff-options">Options</Label>
          <Input
            id="ff-options"
            value={value.options}
            onChange={(e) => change("options", e.target.value)}
            placeholder="e.g. XS, S, M, L, XL"
            required
          />
          <p className="text-xs text-[var(--color-fg-muted)] mt-1">
            Comma-separated list.
          </p>
        </div>
      )}
      <div>
        <Label htmlFor="ff-help">Help text (optional)</Label>
        <Input
          id="ff-help"
          value={value.help_text}
          onChange={(e) => change("help_text", e.target.value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm" htmlFor="ff-required">
        <input
          id="ff-required"
          type="checkbox"
          checked={!!value.required}
          onChange={(e) => change("required", e.target.checked)}
        />
        Required (volunteers should answer this; organizer can override)
      </label>
      <div className="flex items-center justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit">{isEdit ? "Update field" : "Add field"}</Button>
      </div>
    </form>
  );
}

export default function FormFieldsDrawer({
  open,
  onClose,
  title = "Form fields",
  schema,
  onSave,
  saving = false,
}) {
  // Local working copy; replaced when external schema changes + drawer opens.
  const [workSchema, setWorkSchema] = useState(() =>
    Array.isArray(schema) ? schema : []
  );
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorForm, setEditorForm] = useState(emptyField());
  const [editorIndex, setEditorIndex] = useState(null); // null = create

  useEffect(() => {
    if (open) {
      setWorkSchema(Array.isArray(schema) ? schema.map((f) => ({ ...f })) : []);
    }
  }, [open, schema]);

  const sorted = useMemo(
    () =>
      [...workSchema].sort(
        (a, b) => (a.order ?? 0) - (b.order ?? 0) || a.id.localeCompare(b.id),
      ),
    [workSchema],
  );

  function openCreate() {
    setEditorForm(emptyField());
    setEditorIndex(null);
    setEditorOpen(true);
  }
  function openEdit(idx) {
    setEditorForm(fieldToForm(workSchema[idx]));
    setEditorIndex(idx);
    setEditorOpen(true);
  }
  function handleEditorSubmit() {
    const nextField = formToField(editorForm);
    if (!nextField.id || !nextField.label) return;
    setWorkSchema((prev) => {
      const copy = prev.map((f) => ({ ...f }));
      if (editorIndex == null) {
        // Enforce unique id
        if (copy.some((f) => f.id === nextField.id)) return copy;
        if (!nextField.order) {
          nextField.order = (copy.reduce((m, f) => Math.max(m, f.order || 0), 0) || 0) + 1;
        }
        copy.push(nextField);
      } else {
        copy[editorIndex] = { ...copy[editorIndex], ...nextField };
      }
      return copy;
    });
    setEditorOpen(false);
  }
  function handleDelete(idx) {
    setWorkSchema((prev) => prev.filter((_, i) => i !== idx));
  }
  function handleMove(idx, delta) {
    setWorkSchema((prev) => {
      const copy = [...prev];
      const j = idx + delta;
      if (j < 0 || j >= copy.length) return prev;
      [copy[idx], copy[j]] = [copy[j], copy[idx]];
      return copy.map((f, i) => ({ ...f, order: i + 1 }));
    });
  }

  function handleSave() {
    const normalized = workSchema.map((f, i) => ({
      ...f,
      order: f.order || i + 1,
    }));
    onSave && onSave(normalized);
  }

  return (
    <>
      <SideDrawer open={open} onClose={onClose} title={title} widthClass="w-[52rem]">
        <div className="space-y-4">
          <details className="rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-900">
            <summary className="cursor-pointer list-none select-none px-4 py-2.5 font-semibold flex items-center justify-between">
              <span>What are custom questions?</span>
              <span className="text-xs font-normal text-blue-700">Click to expand</span>
            </summary>
            <div className="px-4 pb-3 space-y-2">
              <p>
                Extra questions you want to ask volunteers when they sign up —
                anything beyond name, email, and phone (which are always
                collected). Examples: "Emergency contact", "T-shirt size",
                "Dietary restrictions".
              </p>
              <p className="text-xs">
                Answers show up on the roster and in the CSV export.
              </p>
            </div>
          </details>

          <div className="flex items-center justify-between">
            <p className="text-sm text-[var(--color-fg-muted)]">
              {sorted.length === 0
                ? "No questions yet."
                : `${sorted.length} question${sorted.length === 1 ? "" : "s"}`}
            </p>
            <Button type="button" onClick={openCreate}>
              + Add question
            </Button>
          </div>

          {sorted.length === 0 ? (
            <EmptyState
              title="No custom questions"
              body="Click + Add question to create one, or save with none to keep the signup form simple."
            />
          ) : (
            <ul className="flex flex-col gap-2">
              {sorted.map((f, i) => {
                const realIdx = workSchema.findIndex((x) => x.id === f.id);
                return (
                  <li
                    key={f.id}
                    className="rounded-lg border border-[var(--color-border)] bg-white p-3 flex items-start gap-3"
                  >
                    <div className="flex flex-col items-center gap-0.5 shrink-0">
                      <button
                        type="button"
                        aria-label="Move up"
                        onClick={() => handleMove(realIdx, -1)}
                        disabled={i === 0}
                        className="text-xs px-1.5 rounded hover:bg-gray-100 disabled:opacity-30"
                      >
                        ▲
                      </button>
                      <span className="text-[10px] text-[var(--color-fg-muted)]">{i + 1}</span>
                      <button
                        type="button"
                        aria-label="Move down"
                        onClick={() => handleMove(realIdx, +1)}
                        disabled={i === sorted.length - 1}
                        className="text-xs px-1.5 rounded hover:bg-gray-100 disabled:opacity-30"
                      >
                        ▼
                      </button>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm break-words">{f.label}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-fg-muted)]">
                        <span className="font-mono">{f.id}</span>
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 uppercase tracking-wide">{f.type}</span>
                        {f.required && (
                          <span className="rounded-full bg-red-100 text-red-700 px-2 py-0.5 font-medium">
                            Required
                          </span>
                        )}
                      </div>
                      {f.help_text && (
                        <p className="mt-1 text-xs text-[var(--color-fg-muted)]">{f.help_text}</p>
                      )}
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => openEdit(realIdx)}
                      >
                        Edit
                      </Button>
                      <Button
                        type="button"
                        variant="danger"
                        onClick={() => handleDelete(realIdx)}
                      >
                        Delete
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-[var(--color-border)] sticky bottom-0 bg-white">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save form fields"}
            </Button>
          </div>
        </div>
      </SideDrawer>

      <Modal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        title={editorIndex == null ? "Add field" : "Edit field"}
      >
        <FieldEditor
          value={editorForm}
          onChange={setEditorForm}
          onSubmit={handleEditorSubmit}
          onCancel={() => setEditorOpen(false)}
          isEdit={editorIndex != null}
        />
      </Modal>
    </>
  );
}
