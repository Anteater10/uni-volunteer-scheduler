import React from 'react'
import { cn } from '../../lib/cn'

const PageHeader = React.forwardRef(function PageHeader(
  { title, subtitle, action, className, ...rest },
  ref,
) {
  return (
    <header
      ref={ref}
      className={cn('mb-4 flex items-start justify-between gap-3', className)}
      {...rest}
    >
      <div>
        {/* TODO(copy): page titles supplied by caller */}
        <h1 className="text-[22px] md:text-[28px] font-bold leading-tight">{title}</h1>
        {subtitle ? (
          <p className="text-sm text-[var(--color-fg-muted)] mt-1">{subtitle}</p>
        ) : null}
      </div>
      {action}
    </header>
  )
})

export default PageHeader
export { PageHeader }
