// PLACEHOLDER: minimal ErrorState shipped by Plan 15-04 so the build resolves
// while Plan 15-01 is in flight. Plan 15-01 ships the polished version with
// danger icon + brand styling. API (title, body, action) is locked by UI-SPEC
// §Error states; the merge replaces this file with no API change.
import React from 'react'
import { cn } from '../../lib/cn'

const ErrorState = React.forwardRef(function ErrorState(
  { title, body, action, className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      role="alert"
      aria-live="polite"
      className={cn('py-12 text-center', className)}
      {...rest}
    >
      {title ? (
        <p className="text-lg font-semibold text-[var(--color-fg)]">{title}</p>
      ) : null}
      {body ? (
        <p className="text-sm text-[var(--color-fg-muted)] mt-2">{body}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
})

export default ErrorState
export { ErrorState }
