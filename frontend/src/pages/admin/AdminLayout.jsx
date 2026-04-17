// src/pages/admin/AdminLayout.jsx
import React, {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../state/useAuth";
import DesktopOnlyBanner, {
  useIsDesktop,
} from "../../components/admin/DesktopOnlyBanner";
import AdminTopBar from "../../components/admin/AdminTopBar";

// ---------------------------------------------------------------------------
// AdminPageTitleContext
//
// Sections under /admin/* emit their own breadcrumb label via
// `useAdminPageTitle("Users")` so the top bar shows "Admin / Users" without
// the layout having to hardcode a route-to-label map.
// ---------------------------------------------------------------------------
export const AdminPageTitleContext = createContext({
  title: "",
  setTitle: () => {},
});

export function useAdminPageTitle(title) {
  const ctx = useContext(AdminPageTitleContext);
  useEffect(() => {
    ctx.setTitle(title);
    return () => ctx.setTitle("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title]);
}

// Phase 16 Plan 01 (ADMIN-01): prereq-override nav item retired.
// Phase 17/18 still own Templates + Imports — they stay visible because they
// route to existing sections, but Phase 16 does not redesign them.
const allNavItems = [
  { to: "/admin", label: "Overview", end: true, roles: ["admin"] },
  { to: "/admin/events", label: "Events", roles: ["admin", "organizer"] },
  { to: "/admin/users", label: "Users", roles: ["admin"] },
  { to: "/admin/audit-logs", label: "Audit Logs", roles: ["admin"] },
  { to: "/admin/exports", label: "Exports", roles: ["admin"] },
  { to: "/admin/templates", label: "Templates", roles: ["admin", "organizer"] },
  { to: "/admin/imports", label: "Imports", roles: ["admin", "organizer"] },
  // Phase 21 — orientation credit engine
  {
    to: "/admin/orientation-credits",
    label: "Orientation Credits",
    roles: ["admin"],
  },
  // Phase 24 — scheduled reminder emails
  {
    to: "/admin/reminders",
    label: "Reminders",
    roles: ["admin", "organizer"],
  },
];

function NavItem({ to, label, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `block px-4 py-3 rounded-lg text-base font-medium transition-colors ${
          isActive
            ? "bg-slate-700 text-white"
            : "text-slate-300 hover:bg-slate-800 hover:text-white"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const role = user?.role || "participant";
  const isDesktop = useIsDesktop();
  const [pageTitle, setPageTitle] = useState("");

  const navItems = allNavItems.filter((item) => item.roles.includes(role));

  const rootLabel = role === "organizer" ? "Organizer" : "Admin";
  const rootTarget = role === "organizer" ? "/admin/events" : "/admin";
  const crumbs = [
    { label: rootLabel, to: rootTarget },
    pageTitle ? { label: pageTitle } : null,
  ].filter(Boolean);

  function handleSignOut() {
    if (logout) logout();
    navigate("/login");
  }

  return (
    <AdminPageTitleContext.Provider
      value={{ title: pageTitle, setTitle: setPageTitle }}
    >
      <div className="min-h-screen flex bg-gray-50">
        <aside className="hidden md:flex flex-col w-72 bg-slate-900 text-slate-100 p-5 gap-2">
          <div className="px-4 py-4 text-xl font-semibold tracking-tight">
            {role === "organizer" ? "SciTrek Organizer" : "SciTrek Admin"}
          </div>
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </nav>
          <div className="mt-auto pt-4 border-t border-slate-800">
            <a
              href="/events"
              className="block px-4 py-3 rounded-lg text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            >
              ← View public events page
            </a>
          </div>
        </aside>

        <main className="flex-1 flex flex-col min-w-0">
          <AdminTopBar
            crumbs={crumbs}
            user={user}
            onSignOut={handleSignOut}
          />
          <div className="p-6 flex-1 min-w-0">
            {isDesktop ? <Outlet /> : <DesktopOnlyBanner />}
          </div>
        </main>
      </div>
    </AdminPageTitleContext.Provider>
  );
}
