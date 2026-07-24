// src/pages/admin/QuartersSection.jsx
//
// Standalone /admin/quarters page. Quarters no longer hold a permanent nav
// slot (they're edited ~once a quarter) — day-to-day access is the "Manage
// quarters" drawer on the Overview page. This route still exists for:
//   - first-run setup (the quarter-setup guard redirects here with ?setup=1)
//   - the runway banner's "Enter it in Quarters" link
//   - deep links to the retrospective sub-route (/admin/quarters/:id)
//
// The actual UI lives in QuartersManager; this wrapper only owns the
// breadcrumb title so the drawer host (Overview) doesn't fight over it.

import React from "react";
import QuartersManager from "./QuartersManager";
import { useAdminPageTitle } from "./AdminLayout";

export default function QuartersSection() {
  useAdminPageTitle("Quarters");
  return <QuartersManager />;
}
