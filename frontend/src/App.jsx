// src/App.jsx
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

import EventsBrowsePage from "./pages/public/EventsBrowsePage";
import EventDetailPage from "./pages/public/EventDetailPage";
import PortalPage from "./pages/PortalPage";
import LoginPage from "./pages/LoginPage";
import SetPasswordPage from "./pages/SetPasswordPage";
import NotificationsPage from "./pages/NotificationsPage";
import ProfilePage from "./pages/ProfilePage";

import OrganizerDashboardPage from "./pages/OrganizerDashboardPage";
import OrganizerEventPage from "./pages/OrganizerEventPage";
import OrganizerRosterPage from "./pages/OrganizerRosterPage";

import AdminLayout from "./pages/admin/AdminLayout";
import OverviewSection from "./pages/admin/OverviewSection";
import AdminEventPage from "./pages/AdminEventPage";
import UsersAdminPage from "./pages/UsersAdminPage";
import PortalsAdminPage from "./pages/PortalsAdminPage";
import AuditLogsPage from "./pages/AuditLogsPage";
import ExportsSection from "./pages/admin/ExportsSection";
import TemplatesSection from "./pages/admin/TemplatesSection";
import ImportsSection from "./pages/admin/ImportsSection";
import EventsSection from "./pages/admin/EventsSection";
import HelpSection from "./pages/admin/HelpSection";

import SelfCheckInPage from "./pages/SelfCheckInPage";
import NotFoundPage from "./pages/NotFoundPage";
import ConfirmSignupPage from "./pages/public/ConfirmSignupPage";
import ManageSignupsPage from "./pages/public/ManageSignupsPage";

export default function App() {
  return (
    <Routes>
      {/* Layout wrapper */}
      <Route path="/" element={<Layout />}>
        {/* Public */}
        <Route index element={<Navigate to="/events" replace />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="set-password" element={<SetPasswordPage />} />
        <Route path="events" element={<EventsBrowsePage />} />
        <Route path="events/:eventId" element={<EventDetailPage />} />
        <Route path="portals/:slug" element={<PortalPage />} />
        <Route path="check-in/:signupId" element={<SelfCheckInPage />} />
        <Route path="signup/confirm" element={<ConfirmSignupPage />} />
        <Route path="signup/manage" element={<ManageSignupsPage />} />

        {/* Auth-required — organizer/admin only */}
        <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>

        {/* Organizer/Admin */}
        <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
          <Route path="organizer" element={<OrganizerDashboardPage />} />
          <Route path="organizer/events/:eventId" element={<OrganizerEventPage />} />
          <Route path="organize/events/:eventId/roster" element={<OrganizerRosterPage />} />
        </Route>

        {/* Admin/Organizer — nested under AdminLayout */}
        <Route element={<ProtectedRoute roles={["admin", "organizer"]} />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<OverviewSection />} />
            <Route path="events" element={<EventsSection />} />
            <Route path="events/:eventId" element={<AdminEventPage />} />
            <Route path="users" element={<UsersAdminPage />} />
            <Route path="portals" element={<PortalsAdminPage />} />
            <Route path="audit-logs" element={<AuditLogsPage />} />
            <Route path="templates" element={<TemplatesSection />} />
            <Route path="imports" element={<ImportsSection />} />
            <Route path="exports" element={<ExportsSection />} />
            <Route path="help" element={<HelpSection />} />
          </Route>
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
