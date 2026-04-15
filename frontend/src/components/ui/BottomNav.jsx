import React from 'react'
import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/cn'

const BottomNav = React.forwardRef(function BottomNav({ items = [], className, ...rest }, ref) {
  return (
    <nav
      ref={ref}
      aria-label="Primary"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      className={cn(
        'fixed bottom-0 inset-x-0 z-20 md:hidden border-t border-[var(--color-border)] bg-[var(--color-bg)]/95 backdrop-blur',
        className,
      )}
      {...rest}
    >
      <ul className="mx-auto flex max-w-screen-md">
        {/* NavLink sets aria-current="page" when the route is active */}
        {items.map((item) => (
          <li key={item.to} className="flex-1">
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'flex min-h-14 flex-col items-center justify-center gap-1 text-xs',
                  isActive
                    ? 'text-[var(--color-brand)]'
                    : 'text-[var(--color-fg-muted)]',
                )
              }
            >
              {item.icon}
              {/* TODO(copy): labels come from caller */}
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
})

export default BottomNav
export { BottomNav }
