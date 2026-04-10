// src/App.jsx
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

import EventsPage from "./pages/EventsPage"; // kept on disk — Phase 12 removes it
import EventsBrowsePage from "./pages/public/EventsBrowsePage";
import EventDetailPage from "./pages/public/EventDetailPage";
import PortalPage from "./pages/PortalPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import MySignupsPage from "./pages/MySignupsPage";
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
import OverridesSection from "./pages/admin/OverridesSection";
import TemplatesSection from "./pages/admin/TemplatesSection";
import ImportsSection from "./pages/admin/ImportsSection";

import SelfCheckInPage from "./pages/SelfCheckInPage";
import SignupConfirmedPage from "./pages/SignupConfirmedPage";
import SignupConfirmFailedPage from "./pages/SignupConfirmFailedPage";
import SignupConfirmPendingPage from "./pages/SignupConfirmPendingPage";
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
        <Route path="register" element={<RegisterPage />} />
        <Route path="events" element={<EventsBrowsePage />} />
        <Route path="events/:eventId" element={<EventDetailPage />} />
        <Route path="portals/:slug" element={<PortalPage />} />
        <Route path="check-in/:signupId" element={<SelfCheckInPage />} />
        <Route path="signup/confirmed" element={<SignupConfirmedPage />} />
        <Route path="signup/confirm-failed" element={<SignupConfirmFailedPage />} />
        <Route path="signup/confirm-pending" element={<SignupConfirmPendingPage />} />
        <Route path="signup/confirm" element={<ConfirmSignupPage />} />
        <Route path="signup/manage" element={<ManageSignupsPage />} />

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

        {/* Admin/Organizer — nested under AdminLayout */}
        <Route element={<ProtectedRoute roles={["admin", "organizer"]} />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<OverviewSection />} />
            <Route path="events/:eventId" element={<AdminEventPage />} />
            <Route path="users" element={<UsersAdminPage />} />
            <Route path="portals" element={<PortalsAdminPage />} />
            <Route path="audit-logs" element={<AuditLogsPage />} />
            <Route path="templates" element={<TemplatesSection />} />
            <Route path="imports" element={<ImportsSection />} />
            <Route path="overrides" element={<OverridesSection />} />
            <Route path="exports" element={<ExportsSection />} />
          </Route>
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
