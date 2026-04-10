import React from 'react'
import { cn } from '../../lib/cn'

const Card = React.forwardRef(function Card({ className, ...rest }, ref) {
  return (
    <div
      ref={ref}
      className={cn(
        'rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 md:p-6 shadow-sm',
        className,
      )}
      {...rest}
    />
  )
})

export default Card
export { Card }
