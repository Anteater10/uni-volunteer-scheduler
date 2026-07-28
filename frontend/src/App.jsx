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

function RedirectEventsToVolunteer() {
  return <Navigate to="/volunteer" replace />;
}

function RedirectEventDetailToVolunteer() {
  const { eventId } = useParams();
  return <Navigate to={`/volunteer/events/${eventId}`} replace />;
}

function RootRoute() {
  const { isAuthed, role } = useAuth();
  if (isAuthed && (role === "admin" || role === "organizer")) {
    return <Navigate to="/admin" replace />;
  }
  return <LoginPage />;
}

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

import EventsBrowsePage from "./pages/public/EventsBrowsePage";
import EventDetailPage from "./pages/public/EventDetailPage";
import LoginPage from "./pages/LoginPage";
import SetPasswordPage from "./pages/SetPasswordPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import NotificationsPage from "./pages/NotificationsPage";
import UserSettingsPage from "./pages/UserSettingsPage";

import OrganizerRosterPage from "./pages/OrganizerRosterPage";
import OrganizerDashboard from "./pages/organizer/OrganizerDashboard";

import AdminLayout from "./pages/admin/AdminLayout";
import OverviewSection from "./pages/admin/OverviewSection";
import QuartersSection from "./pages/admin/QuartersSection";
import QuarterRetrospectivePage from "./pages/admin/QuarterRetrospectivePage";
import { useAuth } from "./state/useAuth";

function AdminIndexRoute() {
  const { role } = useAuth();
  if (role === "organizer") return <Navigate to="/admin/operations" replace />;
  return <OverviewSection />;
}
import AdminEventPage from "./pages/AdminEventPage";
import UsersAdminPage from "./pages/UsersAdminPage";
import AuditLogsPage from "./pages/AuditLogsPage";
import ExportsSection from "./pages/admin/ExportsSection";
import ModulesSection from "./pages/admin/ModulesSection";
import OrientationCreditsSection from "./pages/admin/OrientationCreditsSection";
import EventsSection from "./pages/admin/EventsSection";
import HelpSection from "./pages/admin/HelpSection";
// Operations console — folds the former Preview + Reminders tabs into one
// (it renders OrganizerDashboard + AdminRemindersPage internally).
import OperationsPage from "./pages/admin/OperationsPage";
// Phase 35-01 — copilot human-feedback admin page
import AdminCopilotFeedbackPage from "./pages/admin/AdminCopilotFeedbackPage";

import SelfCheckInPage from "./pages/SelfCheckInPage";
import EventCheckInPage from "./pages/EventCheckInPage";
import NotFoundPage from "./pages/NotFoundPage";
import ConfirmSignupPage from "./pages/public/ConfirmSignupPage";
import ManageSignupsPage from "./pages/public/ManageSignupsPage";

export default function App() {
  return (
    <Routes>
      {/* Layout wrapper */}
      <Route path="/" element={<Layout />}>
        {/* Root — admin landing (login if signed out, dashboard if signed in) */}
        <Route index element={<RootRoute />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="set-password" element={<SetPasswordPage />} />
        <Route path="forgot-password" element={<ForgotPasswordPage />} />

        {/* Participant surfaces (no login button anywhere) */}
        <Route path="volunteer" element={<EventsBrowsePage />} />
        <Route path="volunteer/events/:eventId" element={<EventDetailPage />} />

        {/* Legacy /events — redirect to /volunteer so emailed links don't break */}
        <Route path="events" element={<RedirectEventsToVolunteer />} />
        <Route
          path="events/:eventId"
          element={<RedirectEventDetailToVolunteer />}
        />

        <Route path="check-in/:signupId" element={<SelfCheckInPage />} />
        <Route path="event-check-in/:eventId" element={<EventCheckInPage />} />
        <Route path="signup/confirm" element={<ConfirmSignupPage />} />
        <Route path="signup/manage" element={<ManageSignupsPage />} />

        {/* Auth-required — organizer/admin only */}
        <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="settings" element={<UserSettingsPage />} />
          {/* Legacy path — the profile stub became Settings. */}
          <Route path="profile" element={<Navigate to="/settings" replace />} />
        </Route>

        {/* Organizer roster — mobile check-in surface */}
        <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
          <Route path="organizer" element={<Navigate to="/admin/operations" replace />} />
          {/* The same schedule as Operations, but outside the admin shell so it
              renders on a phone. Day-of check-in is a phone job, and every
              other organizer route lives under /admin/* behind the
              desktop-only banner — this is how the roster is reachable at a
              school without a laptop open. */}
          <Route path="organizer/today" element={<OrganizerDashboard />} />
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
            <Route path="operations" element={<OperationsPage />} />
            {/* Legacy paths — folded into Operations; redirect old links. */}
            <Route
              path="preview"
              element={<Navigate to="/admin/operations" replace />}
            />
            <Route path="events/:eventId" element={<AdminEventPage />} />
            <Route
              path="events/:eventId/roster"
              element={<OrganizerRosterPage />}
            />
            <Route path="modules" element={<ModulesSection />} />
            {/* old bookmarks — the route was /admin/templates before PR #51 */}
            <Route path="templates" element={<Navigate to="/admin/modules" replace />} />
            <Route
              path="reminders"
              element={<Navigate to="/admin/operations?tab=reminders" replace />}
            />
            <Route
              path="copilot-feedback"
              element={<AdminCopilotFeedbackPage />}
            />
            <Route path="help" element={<HelpSection />} />
            {/* Admin-only surfaces */}
            <Route element={<ProtectedRoute roles={["admin"]} />}>
              <Route path="quarters" element={<QuartersSection />} />
              {/* Issue #38 — past-quarter retrospective drill-in */}
              <Route
                path="quarters/:quarterId"
                element={<QuarterRetrospectivePage />}
              />
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
