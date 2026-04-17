// src/App.jsx
import React from "react";
import { Routes, Route, Navigate, useParams } from "react-router-dom";

function RedirectEventToAdmin() {
  const { eventId } = useParams();
  return <Navigate to={`/admin/events/${eventId}`} replace />;
}

function RedirectOrganizeRoster() {
  const { eventId } = useParams();
  return <Navigate to={`/organizer/events/${eventId}/roster`} replace />;
}

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

import EventsBrowsePage from "./pages/public/EventsBrowsePage";
import EventDetailPage from "./pages/public/EventDetailPage";
import LoginPage from "./pages/LoginPage";
import SetPasswordPage from "./pages/SetPasswordPage";
import NotificationsPage from "./pages/NotificationsPage";
import ProfilePage from "./pages/ProfilePage";

import OrganizerRosterPage from "./pages/OrganizerRosterPage";
import OrganizerDashboard from "./pages/organizer/OrganizerDashboard";

import AdminLayout from "./pages/admin/AdminLayout";
import OverviewSection from "./pages/admin/OverviewSection";
import { useAuth } from "./state/useAuth";

function AdminIndexRoute() {
  const { role } = useAuth();
  if (role === "organizer") return <Navigate to="/organizer" replace />;
  return <OverviewSection />;
}
import AdminEventPage from "./pages/AdminEventPage";
import UsersAdminPage from "./pages/UsersAdminPage";
import AuditLogsPage from "./pages/AuditLogsPage";
import ExportsSection from "./pages/admin/ExportsSection";
import TemplatesSection from "./pages/admin/TemplatesSection";
import ImportsSection from "./pages/admin/ImportsSection";
import OrientationCreditsSection from "./pages/admin/OrientationCreditsSection";
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
        <Route path="check-in/:signupId" element={<SelfCheckInPage />} />
        <Route path="signup/confirm" element={<ConfirmSignupPage />} />
        <Route path="signup/manage" element={<ManageSignupsPage />} />

        {/* Auth-required — organizer/admin only */}
        <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>

        {/* Organizer roster — mobile check-in surface */}
        <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
          <Route path="organizer" element={<OrganizerDashboard />} />
          <Route path="organizer/events/:eventId" element={<RedirectEventToAdmin />} />
          <Route path="organizer/events/:eventId/roster" element={<OrganizerRosterPage />} />
          {/* Legacy typo path — preserved as redirect for old bookmarks/tests */}
          <Route path="organize/events/:eventId/roster" element={<RedirectOrganizeRoster />} />
        </Route>

        {/* Admin shell — shared surfaces (admin + organizer) */}
        <Route element={<ProtectedRoute roles={["admin", "organizer"]} />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<AdminIndexRoute />} />
            <Route path="events" element={<EventsSection />} />
            <Route path="events/:eventId" element={<AdminEventPage />} />
            <Route path="imports" element={<ImportsSection />} />
            <Route path="templates" element={<TemplatesSection />} />
            <Route path="help" element={<HelpSection />} />
            {/* Admin-only surfaces */}
            <Route element={<ProtectedRoute roles={["admin"]} />}>
              <Route path="users" element={<UsersAdminPage />} />
              <Route path="audit-logs" element={<AuditLogsPage />} />
              <Route path="exports" element={<ExportsSection />} />
              {/* Phase 21 */}
              <Route
                path="orientation-credits"
                element={<OrientationCreditsSection />}
              />
            </Route>
          </Route>
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
