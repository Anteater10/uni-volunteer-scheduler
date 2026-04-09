// src/App.jsx
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

import EventsPage from "./pages/EventsPage";
import EventDetailPage from "./pages/EventDetailPage";
import PortalPage from "./pages/PortalPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import MySignupsPage from "./pages/MySignupsPage";
import NotificationsPage from "./pages/NotificationsPage";
import ProfilePage from "./pages/ProfilePage";

import OrganizerDashboardPage from "./pages/OrganizerDashboardPage";
import OrganizerEventPage from "./pages/OrganizerEventPage";
import OrganizerRosterPage from "./pages/OrganizerRosterPage";

import AdminDashboardPage from "./pages/AdminDashboardPage";
import AdminEventPage from "./pages/AdminEventPage";
import UsersAdminPage from "./pages/UsersAdminPage";
import PortalsAdminPage from "./pages/PortalsAdminPage";
import AuditLogsPage from "./pages/AuditLogsPage";

import SignupConfirmedPage from "./pages/SignupConfirmedPage";
import SignupConfirmFailedPage from "./pages/SignupConfirmFailedPage";
import SignupConfirmPendingPage from "./pages/SignupConfirmPendingPage";
import NotFoundPage from "./pages/NotFoundPage";

export default function App() {
  return (
    <Routes>
      {/* Layout wrapper */}
      <Route path="/" element={<Layout />}>
        {/* Public */}
        <Route index element={<Navigate to="/events" replace />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="events/:eventId" element={<EventDetailPage />} />
        <Route path="portals/:slug" element={<PortalPage />} />
        <Route path="signup/confirmed" element={<SignupConfirmedPage />} />
        <Route path="signup/confirm-failed" element={<SignupConfirmFailedPage />} />
        <Route path="signup/confirm-pending" element={<SignupConfirmPendingPage />} />

        {/* Auth-required (any logged-in user) */}
        <Route element={<ProtectedRoute />}>
          <Route path="my-signups" element={<MySignupsPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>

        {/* Organizer/Admin */}
        <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
          <Route path="organizer" element={<OrganizerDashboardPage />} />
          <Route path="organizer/events/:eventId" element={<OrganizerEventPage />} />
          <Route path="organize/events/:eventId/roster" element={<OrganizerRosterPage />} />
        </Route>

        {/* Admin-only */}
        <Route element={<ProtectedRoute roles={["admin"]} />}>
          <Route path="admin" element={<AdminDashboardPage />} />
          <Route path="admin/events/:eventId" element={<AdminEventPage />} />
          <Route path="admin/users" element={<UsersAdminPage />} />
          <Route path="admin/portals" element={<PortalsAdminPage />} />
          <Route path="admin/audit-logs" element={<AuditLogsPage />} />
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
