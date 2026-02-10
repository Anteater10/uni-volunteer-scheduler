// src/components/ProtectedRoute.jsx
import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../state/authContext";

export default function ProtectedRoute({ roles = null, children }) {
  const { initializing, isAuthed, role } = useAuth();

  if (initializing) return <div style={{ padding: 16 }}>Loading…</div>;
  if (!isAuthed) return <Navigate to="/login" replace />;

  if (roles && Array.isArray(roles) && roles.length > 0 && !roles.includes(role)) {
    return (
      <div style={{ padding: 16 }}>
        <h2>Forbidden</h2>
        <p>Your account does not have access to this page.</p>
      </div>
    );
  }

  // If used as wrapper: <ProtectedRoute><Page/></ProtectedRoute>
  if (children) return children;

  // If used as nested route element: <Route element={<ProtectedRoute/>}><Route .../></Route>
  return <Outlet />;
}
