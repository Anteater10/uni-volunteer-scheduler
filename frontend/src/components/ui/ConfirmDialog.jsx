// K13/K14 — one confirmation dialog for every destructive action.
//
// Before this, the strength of a dialog had nothing to do with how bad the
// action was. Archiving a module — reversible with one click — got the real
// `Modal`: portalled, `role="dialog"`, focus-trapped, Escape-closable.
// Deleting an event, which takes the event, its slots and every signup on
// them, got a bare `<div>` with none of that. Deactivating a user got no
// dialog at all, one click away from a type-to-confirm CCPA delete in the
// same drawer.
//
// Built on `Modal` so the accessibility behaviour is inherited rather than
// re-implemented, and so there is exactly one place left to fix if it is ever
// wrong again.
//
// `requireTyped` escalates to type-to-confirm for the actions that destroy
// data outright: the button stays disabled until the operator types the exact
// string, which makes it impossible to confirm by muscle memory.

import React, { useEffect, useState } from 'react'
import Modal from './Modal'
import Button from './Button'
import Input from './Input'
import Label from './Label'

export default function ConfirmDialog({
  open,
  title,
  body,
  // Named for the action, not for the widget: "Delete event" tells the
  // operator what the click does; "OK" does not.
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  busyLabel,
  onCancel,
  onConfirm,
  busy = false,
  // When set, the operator must type this exact string before confirming.
  requireTyped = null,
  requireTypedHint,
}) {
  const [typed, setTyped] = useState('')

  // Reset between openings, otherwise the previous target's text would still
  // be sitting in the box and arm the button for a different record.
  useEffect(() => {
    if (!open) setTyped('')
  }, [open])

  if (!open) return null

  const armed = requireTyped ? typed === requireTyped : true

  return (
    <Modal open onClose={busy ? undefined : onCancel} title={title}>
      <p className="text-sm text-[var(--color-fg-muted)]">{body}</p>

      {requireTyped ? (
        <div className="mt-3">
          <Label htmlFor="confirm-dialog-typed">
            {requireTypedHint || `Type "${requireTyped}" to confirm:`}
          </Label>
          <Input
            id="confirm-dialog-typed"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={requireTyped}
            autoComplete="off"
          />
        </div>
      ) : null}

      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button
          type="button"
          variant="danger"
          onClick={onConfirm}
          disabled={busy || !armed}
        >
          {busy ? busyLabel || `${confirmLabel}…` : confirmLabel}
        </Button>
      </div>
    </Modal>
  )
}

export { ConfirmDialog }
