// src/pages/admin/AdminLayout.jsx
import React from "react";
import { Outlet, NavLink } from "react-router-dom";
import { PageHeader } from "../../components/ui";
import { useAuth } from "../../state/useAuth";

const allNavItems = [
  // TODO(copy): nav labels
  { to: "/admin", label: "Overview", end: true, roles: ["admin", "organizer"] },
  { to: "/admin/audit-logs", label: "Audit Log", roles: ["admin"] },
  { to: "/admin/templates", label: "Templates", roles: ["admin"] },
  { to: "/admin/imports", label: "Imports", roles: ["admin", "organizer"] },
  // Phase 16 Plan 01 (ADMIN-01): prereq-override nav item retired.
  { to: "/admin/users", label: "Users", roles: ["admin"] },
  { to: "/admin/exports", label: "Exports", roles: ["admin"] },
];

function NavItem({ to, label, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `block px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
          isActive
            ? "bg-[var(--color-bg-active,#e5e7eb)] text-[var(--color-fg)]"
            : "text-[var(--color-fg-muted)] hover:bg-[var(--color-bg-active,#f3f4f6)]"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export default function AdminLayout() {
  const { user } = useAuth();
  const role = user?.role || "participant";

  const navItems = allNavItems.filter((item) => item.roles.includes(role));

  return (
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="Admin" />

      {/* Mobile: horizontal scrollable tabs */}
      <nav className="md:hidden overflow-x-auto -mx-4 px-4">
        <div className="flex gap-1 min-w-max">
          {navItems.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </div>
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          {/* TODO(copy) */}
          Open on desktop for full view
        </p>
      </nav>

      {/* Desktop: sidebar + content */}
      <div className="hidden md:grid md:grid-cols-[200px_1fr] md:gap-6">
        <nav className="space-y-1">
          {navItems.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>
        <div className="min-w-0">
          <Outlet />
        </div>
      </div>

      {/* Mobile content area (rendered below tabs) */}
      <div className="md:hidden">
        <Outlet />
      </div>
    </div>
  );
}
