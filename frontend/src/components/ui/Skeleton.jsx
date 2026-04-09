import React from 'react'
import { cn } from '../../lib/cn'

const Skeleton = React.forwardRef(function Skeleton({ className, ...rest }, ref) {
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={cn('animate-pulse rounded-md bg-[var(--color-surface)]', className)}
      {...rest}
    />
  )
})

export default Skeleton
export { Skeleton }
