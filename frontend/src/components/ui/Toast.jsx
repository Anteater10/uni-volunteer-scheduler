import React from 'react'
import { cn } from '../../lib/cn'
import { useToasts, dismissToast } from '../../state/toast'

const KIND_CLASSES = {
  success: 'bg-[var(--color-success)] text-white',
  error: 'bg-[var(--color-danger)] text-white',
  info: 'bg-[var(--color-fg)] text-[var(--color-bg)]',
}

export function ToastHost() {
  const toasts = useToasts()
  if (!toasts || toasts.length === 0) return null
  return (
    <div
      className="fixed left-1/2 -translate-x-1/2 bottom-24 md:bottom-6 md:left-auto md:right-6 md:translate-x-0 z-50 flex flex-col gap-2"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          aria-live="polite"
          onClick={() => dismissToast(t.id)}
          className={cn(
            'rounded-lg px-4 py-3 shadow-lg text-sm cursor-pointer',
            KIND_CLASSES[t.kind] || KIND_CLASSES.info,
          )}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}

export default ToastHost
