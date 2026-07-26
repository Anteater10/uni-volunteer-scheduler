// src/pages/admin/AdminLayout.jsx
import React, {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";
import { Link, Outlet, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuth } from "../../state/useAuth";
import DesktopOnlyBanner, {
  useIsDesktop,
} from "../../components/admin/DesktopOnlyBanner";
import AdminTopBar from "../../components/admin/AdminTopBar";
import { useQuarters } from "../../lib/useQuarters";
import { activeQuarters } from "../../lib/weekUtils";

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
    // Pass null/undefined to opt out of breadcrumb management — used by
    // sections rendered embedded inside another page (e.g. the Operations
    // page hosts Reminders) so they don't clobber the host's title.
    if (title == null) return undefined;
    ctx.setTitle(title);
    return () => ctx.setTitle("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title]);
}

// Nav is ordered by an admin's actual workflow, grouped by domain:
//   1. Home            — Overview
//   2. Core event work — Events → Operations (create events, then run them)
//   3. Content library — Modules (the modules events draw from)
//   4. People/credits  — Orientation Credits → Users
//   5. Oversight/data  — Exports → Audit Logs (Audit Logs is toggle-gated)
//   6. Advanced        — Copilot feedback (flag-gated)
// Quarters (Issue #24) is intentionally NOT here — it's edited ~once a
// quarter, so it lives in the "Manage quarters" drawer on Overview. Its
// /admin/quarters route still exists for setup + retrospective.
const allNavItems = [
  // 1. Home
  { to: "/admin", label: "Overview", end: true, roles: ["admin"] },

  // 2. Core event work
  { to: "/admin/events", label: "Events", roles: ["admin", "organizer"] },
  // Day-of console: schedule/rosters + reminder-email queue (formerly the
  // separate "Preview" and "Reminders" tabs).
  { to: "/admin/operations", label: "Operations", roles: ["admin", "organizer"] },

  // 3. Content library the events are built from
  // Labelled "Modules" for admins; the route/table stay "templates".
  { to: "/admin/templates", label: "Modules", roles: ["admin", "organizer"] },

  // 4. People + credits
  // Phase 21 — orientation credit engine
  {
    to: "/admin/orientation-credits",
    label: "Orientation Credits",
    roles: ["admin"],
  },
  { to: "/admin/users", label: "Users", roles: ["admin"] },

  // 5. Oversight + data out
  { to: "/admin/exports", label: "Exports", roles: ["admin"] },
  { to: "/admin/audit-logs", label: "Audit Logs", roles: ["admin"] },

  // 6. Advanced — Phase 35-01 copilot human-feedback aggregates. Hidden
  // alongside the FAB when the copilot flag is off (same gate as CopilotFab).
  {
    to: "/admin/copilot-feedback",
    label: "Copilot feedback",
    roles: ["admin", "organizer"],
    copilotOnly: true,
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
  const location = useLocation();
  const role = user?.role || "participant";
  const isDesktop = useIsDesktop();
  const [pageTitle, setPageTitle] = useState("");

  // Issue #24 — quarter setup guard. With zero quarters entered, every
  // quarter-dependent feature is blocked, so send admins straight to the
  // setup page. Separately, warn when today is uncovered with nothing
  // upcoming — time to transcribe the next quarter's dates.
  const quartersQ = useQuarters();
  const quarters = quartersQ.data;
  const onQuartersPage = location.pathname.startsWith("/admin/quarters");
  useEffect(() => {
    if (role !== "admin" || onQuartersPage) return;
    if (Array.isArray(quarters) && quarters.length === 0) {
      navigate("/admin/quarters?setup=1", { replace: true });
    }
  }, [role, onQuartersPage, quarters, navigate]);

  const todayIso = new Date().toISOString().slice(0, 10);
  const liveQuarters = activeQuarters(quarters || []);
  const showRunwayBanner =
    role === "admin" &&
    Array.isArray(quarters) &&
    quarters.length > 0 &&
    !liveQuarters.some((q) => q.start_date <= todayIso && q.end_date >= todayIso) &&
    !liveQuarters.some((q) => q.start_date > todayIso);

  // Evaluated per render (not module scope) so tests can stub the env var.
  const copilotEnabled =
    import.meta.env.VITE_COPILOT_ENABLED === "true" ||
    import.meta.env.VITE_COPILOT_ENABLED === "1";
  // Audit Logs tab is gated behind a site setting (off by default). Shares
  // the ["adminSiteSettings"] cache key with SiteSettingsCard so toggling it
  // there updates this nav live. Admin-only; organizers can't read settings.
  const siteSettingsQ = useQuery({
    queryKey: ["adminSiteSettings"],
    queryFn: () => api.admin.siteSettings.get(),
    enabled: role === "admin" && typeof api?.admin?.siteSettings?.get === "function",
  });
  const showAuditLogs = siteSettingsQ.data?.show_audit_logs_tab ?? false;

  const navItems = allNavItems.filter(
    (item) =>
      item.roles.includes(role) &&
      (!item.copilotOnly || copilotEnabled) &&
      (item.to !== "/admin/audit-logs" || showAuditLogs),
  );

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
            {showRunwayBanner && (
              <div
                role="status"
                className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
              >
                No upcoming quarter is entered — scheduling is paused until
                you add the next quarter's dates.{" "}
                <Link to="/admin/quarters" className="font-semibold underline">
                  Enter it in Quarters
                </Link>
                .
              </div>
            )}
            {isDesktop ? <Outlet /> : <DesktopOnlyBanner />}
          </div>
        </main>
      </div>
    </AdminPageTitleContext.Provider>
  );
}
