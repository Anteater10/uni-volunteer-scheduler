// layout.jsx
import React, { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Calendar, User, LayoutDashboard, Shield, ClipboardList } from "lucide-react";
import { useAuth } from "../state/useAuth";
import ToastHost from "./ui/Toast";
import BottomNav from "./ui/BottomNav";

const organizerNavItems = [
  { to: "/admin/events", label: "Events", icon: <Calendar className="h-5 w-5" /> },
  { to: "/admin/templates", label: "Templates", icon: <ClipboardList className="h-5 w-5" /> },
  { to: "/admin/imports", label: "Imports", icon: <LayoutDashboard className="h-5 w-5" /> },
  { to: "/profile", label: "Profile", icon: <User className="h-5 w-5" /> },
];

const adminNavItems = [
  // TODO(copy)
  { to: "/admin", label: "Admin", icon: <Shield className="h-5 w-5" /> },
  // TODO(copy)
  { to: "/admin/users", label: "Users", icon: <User className="h-5 w-5" /> },
  // TODO(copy)
  { to: "/admin/audit-logs", label: "Logs", icon: <ClipboardList className="h-5 w-5" /> },
];

function navItemsForRole(role) {
  switch (role) {
    case "organizer":
      return organizerNavItems;
    case "admin":
      return adminNavItems;
    default:
      return null;
  }
}

export default function Layout() {
  const { user, isAuthed, role, logout } = useAuth();
  const navItems = isAuthed ? navItemsForRole(role) : null;
  const { pathname } = useLocation();
  const isAdminRoute = pathname.startsWith("/admin");
  const containerWidth = isAdminRoute ? "max-w-none" : "max-w-screen-md";
  const brandTarget =
    isAuthed && role === "admin"
      ? "/admin"
      : isAuthed && role === "organizer"
        ? "/admin/events"
        : "/events";
  const helpTarget =
    role === "admin" || role === "organizer" ? "/admin/help" : "/help";

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  useEffect(() => {
    if (!menuOpen) return undefined;
    function onKey(e) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    function onClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [menuOpen]);

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-bg)] text-[var(--color-fg)]">
      <header className="sticky top-0 z-30 h-14 border-b border-[var(--color-border)] bg-[var(--color-bg)]/95 backdrop-blur">
        <div className={`mx-auto flex h-full ${containerWidth} items-center justify-between px-4`}>
          <Link to={brandTarget} className="font-semibold">
            Volunteer Scheduler
          </Link>
          <div className="flex items-center gap-3 text-sm">
            {isAuthed ? (
              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((o) => !o)}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-gray-100"
                >
                  <span className="text-[var(--color-fg-muted)]">
                    {user?.email} ({role})
                  </span>
                  <span aria-hidden="true" className="text-xs">▾</span>
                </button>
                {menuOpen ? (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-48 rounded-lg border border-gray-200 bg-white p-2 shadow-lg z-50"
                  >
                    <Link
                      to={helpTarget}
                      role="menuitem"
                      onClick={() => setMenuOpen(false)}
                      className="block rounded-md px-2 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      Help
                    </Link>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMenuOpen(false);
                        logout && logout();
                      }}
                      className="w-full rounded-md px-2 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-100"
                    >
                      Logout
                    </button>
                  </div>
                ) : null}
              </div>
            ) : (
              <Link to="/login">Login</Link>
            )}
          </div>
        </div>
      </header>

      <main className={`flex-1 mx-auto w-full ${containerWidth} ${isAdminRoute ? "" : "px-4 pb-20 md:pb-8"}`}>
        <Outlet />
      </main>

      <div id="bottom-nav-slot">
        {navItems && <BottomNav items={navItems} />}
      </div>
      <ToastHost />
    </div>
  );
}
