// TODO(copy): Toast messages are supplied by callers. Copy belongs at call sites.
import { useSyncExternalStore } from 'react'

let toasts = []
const listeners = new Set()
const timers = new Map()

function emit() {
  toasts = [...toasts]
  listeners.forEach((l) => l())
}

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot() {
  return toasts
}

export function dismissToast(id) {
  const timer = timers.get(id)
  if (timer) {
    clearTimeout(timer)
    timers.delete(id)
  }
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}

let idCounter = 0
function push(kind, message, opts = {}) {
  const duration = opts.duration ?? 3500
  const id = ++idCounter
  toasts = [...toasts, { id, kind, message, duration }]
  emit()
  if (duration > 0) {
    const handle = setTimeout(() => dismissToast(id), duration)
    timers.set(id, handle)
  }
  return id
}

export const toast = {
  success: (message, opts) => push('success', message, opts),
  error: (message, opts) => push('error', message, opts),
  info: (message, opts) => push('info', message, opts),
}

export function useToasts() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

export default toast
