import React from "react";
import { useAdminPageTitle } from "./AdminLayout";
import Card from "../../components/ui/Card";
import AdminPageHeader from "../../components/admin/AdminPageHeader";
import { useAuth } from "../../state/useAuth";

// `adminOnly` cards describe Users, Audit Logs and Exports — tabs an organizer
// has no route to. Showing them to everyone meant most of an organizer's Help
// page was instructions for buttons they could never find, and the two things
// they actually do every event weren't covered at all.
const SECTIONS = [
  {
    title: "How to invite a new user",
    adminOnly: true,
    body: "Go to Users, click 'Invite new user', enter their name, email, and role (admin or organizer). They'll get an email with a link to sign in — no password needed. The link expires in 15 minutes.",
  },
  {
    title: "How to read the audit log",
    adminOnly: true,
    body: "Audit Logs shows every important change to the system. Use the filters at the top to narrow down by who, what, or when. Click any row to see the full details including raw data.",
  },
  {
    title: "How to export a CSV report",
    adminOnly: true,
    body: "Go to Exports. Pick a time range (This quarter, Last quarter, or custom). Each panel has a 'Download CSV' button that downloads the report to your computer.",
  },
  {
    title: "How to handle a CCPA data request",
    adminOnly: true,
    body: "Go to Users, find the person's row, and click 'CCPA Data Export' to download everything we have on them. Click 'CCPA Delete Account' to permanently anonymize their data. These actions are logged.",
  },
  {
    title: "How to deactivate a user who left",
    adminOnly: true,
    body: "Go to Users, open the user's drawer, and click 'Deactivate'. They can no longer sign in, but their history stays. Click 'Show deactivated' at the top of the list to find them again if you need to reactivate.",
  },
  {
    title: "How to find a specific audit entry",
    adminOnly: true,
    body: "Use the search box in Audit Logs — it matches the name of the person, the action they took, or the target of the action. Combine it with the kind filter and the date range for best results.",
  },
  {
    title: "How to check volunteers in on the day",
    body: "Open the event from Events or Operations and click 'Live roster (check-in)'. Volunteers are grouped by session; tap a name to check them in, tap again to undo. The 4-digit venue code at the top is what volunteers type if they check themselves in on their phone.",
  },
  {
    title: "How to close out a session once it's over",
    body: "On the live roster, click 'End slot' (or 'End event' to do them all). Everyone still not checked in is set to no-show by default — tick anyone who did turn up but wasn't tapped in, then Save. Ending a session is what records attendance, so do it before you leave.",
  },
  {
    title: "How to promote someone off the waitlist",
    body: "Open the event and click 'Promote' on their row. If the session is already full you'll be asked to confirm going one over capacity — say yes only if the room and kits can take it.",
  },
  {
    title: "Why is the admin site desktop-only?",
    body: "Admin work involves lots of tables and details that don't fit well on a phone. If you're on a phone, you'll see a message asking you to switch to a laptop or tablet (anything ≥ 768px wide works). The live roster is the exception — it's built for phones, so use that for day-of check-in.",
  },
  {
    title: "Who to contact for backend issues",
    body: "Reach out to Andy (project owner) in the daily sync. For urgent issues outside sync hours, email siddhantandy@gmail.com. File database corruption under 'urgent'; UI glitches under 'normal'.",
  },
];

export default function HelpSection() {
  useAdminPageTitle("Help");
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const sections = SECTIONS.filter((s) => isAdmin || !s.adminOnly);
  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <AdminPageHeader
          title={isAdmin ? "Admin Help" : "Organizer Help"}
          subtitle="Short how-to answers for the most common tasks. Each card answers one question."
        />
      </div>
      <div className="space-y-4">
        {sections.map((s) => (
          <Card key={s.title}>
            <h2 className="font-semibold mb-2">{s.title}</h2>
            <p className="text-gray-700">{s.body}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
