// layout.jsx
import React from "react";
import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../state/authContext";

export default function Layout() {
  const { user, isAuthed, role, logout } = useAuth();

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <header style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Link to="/events" style={{ fontWeight: 700, textDecoration: "none" }}>UVSE</Link>
          <Link to="/events">Events</Link>
          <Link to="/my-signups">My Signups</Link>
          <Link to="/notifications">Notifications</Link>

          {(role === "organizer" || role === "admin") && (
            <Link to="/organizer">Organizer</Link>
          )}
          {role === "admin" && (
            <Link to="/admin">Admin</Link>
          )}
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {isAuthed ? (
            <>
              <span style={{ opacity: 0.8 }}>
                {user?.email} <span style={{ fontSize: 12 }}>({role})</span>
              </span>
              <button onClick={logout}>Logout</button>
            </>
          ) : (
            <>
              <Link to="/login">Login</Link>
              <Link to="/register">Register</Link>
            </>
          )}
        </div>
      </header>

      <hr style={{ margin: "16px 0" }} />
      <Outlet />
    </div>
  );
}
