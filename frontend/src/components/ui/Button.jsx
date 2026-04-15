import React from 'react'
import { cn } from '../../lib/cn'

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[var(--color-brand)] disabled:opacity-50 disabled:cursor-not-allowed'

const SIZES = {
  md: 'min-h-11 px-4 text-base',
  lg: 'min-h-[52px] px-5 text-base',
}

const VARIANTS = {
  primary:
    'bg-[var(--color-brand)] text-[var(--color-brand-fg)] hover:opacity-90',
  secondary:
    'border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-fg)] hover:bg-[var(--color-surface)]',
  ghost:
    'bg-transparent text-[var(--color-fg)] hover:bg-[var(--color-surface)]',
  danger: 'bg-[var(--color-danger)] text-white hover:opacity-90',
}

const Button = React.forwardRef(function Button(
  { variant = 'primary', size = 'md', as: Comp = 'button', className, type, ...rest },
  ref,
) {
  const classes = cn(BASE, SIZES[size], VARIANTS[variant], className)
  const extra = Comp === 'button' ? { type: type || 'button' } : {}
  return <Comp ref={ref} className={classes} {...extra} {...rest} />
})

export default Button
export { Button }
