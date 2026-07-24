// src/pages/admin/OperationsPage.jsx
//
// "Operations" — the day-of / near-term event console. Consolidates surfaces
// that used to be separate nav tabs into ONE flat tab bar:
//   - Today / Upcoming / Past: the schedule with roster launch
//                              (the former "Preview" — OrganizerDashboard)
//   - Reminders:               the outbound reminder-email queue for the next
//                              7 days (the former "Reminders" tab)
//
// Both were their own tabs when organizers had no accounts; now that
// organizers log in and land here, folding them into one Operations entry
// keeps the admin nav uncluttered. A single flat tab row (no nesting) drives
// everything: the three schedule scopes render OrganizerDashboard with a
// controlled scope, and Reminders renders the queue. Each sub-view is
// rendered `embedded` so this page owns the header/breadcrumb.

import React from "react";
import { useSearchParams } from "react-router-dom";

import AdminPageHeader from "../../components/admin/AdminPageHeader";
import { useAdminPageTitle } from "./AdminLayout";
import OrganizerDashboard from "../organizer/OrganizerDashboard";
import AdminRemindersPage from "./AdminRemindersPage";

const TABS = [
  { id: "today", label: "Today" },
  { id: "upcoming", label: "Upcoming" },
  { id: "past", label: "Past" },
  { id: "reminders", label: "Reminders" },
];
const SCHEDULE_SCOPES = new Set(["today", "upcoming", "past"]);

export default function OperationsPage() {
  useAdminPageTitle("Operations");
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("tab");
  const tab = TABS.some((t) => t.id === raw) ? raw : "today";

  function selectTab(id) {
    // Keep it in the URL so the tab survives refresh / deep links, and so
    // legacy /admin/reminders can redirect straight to the Reminders view.
    setSearchParams(id === "today" ? {} : { tab: id }, { replace: true });
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Operations"
        subtitle="Day-of schedule and the reminder-email queue."
      />

      {/* One flat, full-width tab bar — no nesting. The three schedule scopes
          and Reminders are peers; the underline strip spans the page like a
          real page-level tab bar. */}
      <div className="border-b border-gray-200">
        <nav
          role="tablist"
          aria-label="Operations views"
          className="-mb-px flex gap-8"
        >
          {TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={active}
                onClick={() => selectTab(t.id)}
                className={
                  "whitespace-nowrap border-b-2 px-1 pb-3 pt-1 text-base font-medium transition " +
                  (active
                    ? "border-blue-600 text-blue-700"
                    : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700")
                }
              >
                {t.label}
              </button>
            );
          })}
        </nav>
      </div>

      {SCHEDULE_SCOPES.has(tab) ? (
        <OrganizerDashboard embedded scope={tab} />
      ) : (
        <AdminRemindersPage embedded />
      )}
    </div>
  );
}
