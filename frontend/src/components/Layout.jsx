// layout.jsx
import React from "react";
import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../state/authContext";

export default function Layout() {
  const { user, isAuthed, role, logout } = useAuth();

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

      <div id="bottom-nav-slot" />
    </div>
  );
}
