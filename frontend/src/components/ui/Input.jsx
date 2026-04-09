import React from 'react'
import { cn } from '../../lib/cn'

const Input = React.forwardRef(function Input({ className, type = 'text', ...rest }, ref) {
  return (
    <input
      ref={ref}
      type={type}
      className={cn(
        'min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base text-[var(--color-fg)] placeholder:text-[var(--color-fg-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
        className,
      )}
      {...rest}
    />
  )
})

export default Input
export { Input }
