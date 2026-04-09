import React from 'react'
import { cn } from '../../lib/cn'

const Chip = React.forwardRef(function Chip(
  { active = false, className, children, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type || 'button'}
      aria-pressed={active}
      className={cn(
        'inline-flex min-h-11 items-center rounded-full px-4 text-sm font-medium border border-[var(--color-border)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
        active
          ? 'bg-[var(--color-brand)] text-[var(--color-brand-fg)] border-[var(--color-brand)]'
          : 'bg-[var(--color-bg)] text-[var(--color-fg)] hover:bg-[var(--color-surface)]',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
})

export default Chip
export { Chip }
