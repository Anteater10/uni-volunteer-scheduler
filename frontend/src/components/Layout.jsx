// layout.jsx
import React from "react";
import { Link, Outlet } from "react-router-dom";
import { Calendar, ListChecks, User, LayoutDashboard, Shield, ClipboardList } from "lucide-react";
import { useAuth } from "../state/useAuth";
import ToastHost from "./ui/Toast";
import BottomNav from "./ui/BottomNav";

const studentNavItems = [
  // TODO(copy): bottom-nav labels
  { to: "/events", label: "Events", icon: <Calendar className="h-5 w-5" /> },
  // TODO(copy)
  { to: "/my-signups", label: "My Signups", icon: <ListChecks className="h-5 w-5" /> },
  // TODO(copy)
  { to: "/profile", label: "Profile", icon: <User className="h-5 w-5" /> },
];

const organizerNavItems = [
  // TODO(copy)
  { to: "/organizer", label: "Dashboard", icon: <LayoutDashboard className="h-5 w-5" /> },
  // TODO(copy)
  { to: "/events", label: "Events", icon: <Calendar className="h-5 w-5" /> },
  // TODO(copy)
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
    case "participant":
      return studentNavItems;
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

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-bg)] text-[var(--color-fg)]">
      <header className="sticky top-0 z-30 h-14 border-b border-[var(--color-border)] bg-[var(--color-bg)]/95 backdrop-blur">
        <div className="mx-auto flex h-full max-w-screen-md items-center justify-between px-4">
          {/* TODO(brand): logo/wordmark */}
          <Link to="/events" className="font-semibold">
            {/* TODO(copy): brand wordmark */}
            Volunteer Scheduler
          </Link>
          <div className="flex items-center gap-3 text-sm">
            {isAuthed ? (
              <>
                <span className="hidden sm:inline text-[var(--color-fg-muted)]">
                  {/* TODO(copy) */}
                  {user?.email} ({role})
                </span>
                <button onClick={logout} className="px-2 py-1">
                  {/* TODO(copy) */}
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link to="/login">{/* TODO(copy) */}Login</Link>
                <Link to="/register">{/* TODO(copy) */}Register</Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-screen-md px-4 pb-20 md:pb-8">
        <Outlet />
      </main>

      <div id="bottom-nav-slot">
        {navItems && <BottomNav items={navItems} />}
      </div>
      <ToastHost />
    </div>
  );
}
