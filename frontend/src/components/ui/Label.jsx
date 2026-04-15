import React from 'react'
import { cn } from '../../lib/cn'

const Label = React.forwardRef(function Label({ className, ...rest }, ref) {
  return (
    <label
      ref={ref}
      className={cn('block text-sm font-medium text-[var(--color-fg)] mb-1', className)}
      {...rest}
    />
  )
})

export default Label
export { Label }
