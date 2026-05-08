import React from 'react'
import { AlertTriangle } from 'lucide-react'
import { cn } from '../../lib/cn'

const ErrorState = React.forwardRef(function ErrorState(
  { title, body, action, icon, className, ...rest },
  ref,
) {
  const Icon = icon || AlertTriangle
  return (
    <div
      ref={ref}
      role="alert"
      className={cn('py-12 text-center', className)}
      {...rest}
    >
      <Icon
        aria-hidden="true"
        className="mx-auto mb-3 h-8 w-8 text-[var(--color-danger)]"
      />
      {title ? <p className="text-lg font-semibold">{title}</p> : null}
      {body ? (
        <p className="text-sm text-[var(--color-fg-muted)] mt-2">{body}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
})

export default ErrorState
export { ErrorState }
