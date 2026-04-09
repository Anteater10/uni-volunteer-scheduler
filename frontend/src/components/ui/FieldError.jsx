import React from 'react'
import { cn } from '../../lib/cn'

const FieldError = React.forwardRef(function FieldError({ className, children, ...rest }, ref) {
  if (!children) return null
  return (
    <p
      ref={ref}
      role="alert"
      className={cn('mt-1 text-sm text-[var(--color-danger)]', className)}
      {...rest}
    >
      {children}
    </p>
  )
})

export default FieldError
export { FieldError }
