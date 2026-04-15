import React from 'react'
import { cn } from '../../lib/cn'

const EmptyState = React.forwardRef(function EmptyState(
  { title, body, action, className, ...rest },
  ref,
) {
  return (
    <div ref={ref} className={cn('py-12 text-center', className)} {...rest}>
      {/* TODO(copy): supplied by caller */}
      {title ? <p className="text-lg font-semibold">{title}</p> : null}
      {body ? (
        <p className="text-sm text-[var(--color-fg-muted)] mt-2">{body}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
})

export default EmptyState
export { EmptyState }
