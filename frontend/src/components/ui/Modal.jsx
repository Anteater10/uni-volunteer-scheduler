import React, { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../lib/cn'
import { useFocusTrap } from '../../lib/useFocusTrap'

const Modal = React.forwardRef(function Modal(
  { open, onClose, title, children, className, ...rest },
  _ref,
) {
  const dialogRef = useRef(null)
  const titleId = useId()

  useFocusTrap(dialogRef, !!open)

  useEffect(() => {
    if (!open) return
    const node = dialogRef.current
    if (!node) return
    const handler = () => {
      if (typeof onClose === 'function') onClose()
    }
    node.addEventListener('focustrap-escape', handler)
    return () => node.removeEventListener('focustrap-escape', handler)
  }, [open, onClose])

  if (!open) return null
  if (typeof document === 'undefined') return null

  const handleBackdrop = () => {
    if (typeof onClose === 'function') onClose()
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-black/50"
      onMouseDown={handleBackdrop}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? `modal-title-${titleId}` : undefined}
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
        className={cn(
          'mx-auto w-full max-w-md mt-[15vh] rounded-2xl bg-[var(--color-bg)] p-5 shadow-xl',
          className,
        )}
        {...rest}
      >
        {title ? (
          <h2
            id={`modal-title-${titleId}`}
            className="text-lg font-semibold mb-3"
          >
            {title}
          </h2>
        ) : null}
        {children}
      </div>
    </div>,
    document.body,
  )
})

export default Modal
export { Modal }
