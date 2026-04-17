import React from "react";
import { useAdminPageTitle } from "./AdminLayout";
import Card from "../../components/ui/Card";

const SECTIONS = [
  {
    title: "How to invite a new user",
    body: "Go to Users, click 'Invite new user', enter their name, email, and role (admin or organizer). They'll get an email with a link to sign in — no password needed. The link expires in 15 minutes.",
  },
  {
    title: "How to read the audit log",
    body: "Audit Logs shows every important change to the system. Use the filters at the top to narrow down by who, what, or when. Click any row to see the full details including raw data.",
  },
  {
    title: "How to export a CSV report",
    body: "Go to Exports. Pick a time range (This quarter, Last quarter, or custom). Each panel has a 'Download CSV' button that downloads the report to your computer.",
  },
  {
    title: "How to handle a CCPA data request",
    body: "Go to Users, find the person's row, and click 'CCPA Data Export' to download everything we have on them. Click 'CCPA Delete Account' to permanently anonymize their data. These actions are logged.",
  },
  {
    title: "How to deactivate a user who left",
    body: "Go to Users, open the user's drawer, and click 'Deactivate'. They can no longer sign in, but their history stays. Click 'Show deactivated' at the top of the list to find them again if you need to reactivate.",
  },
  {
    title: "How to find a specific audit entry",
    body: "Use the search box in Audit Logs — it matches the name of the person, the action they took, or the target of the action. Combine it with the kind filter and the date range for best results.",
  },
  {
    title: "Why is the admin site desktop-only?",
    body: "Admin work involves lots of tables and details that don't fit well on a phone. If you're on a phone, you'll see a message asking you to switch to a laptop or tablet (anything ≥ 768px wide works).",
  },
  {
    title: "Who to contact for backend issues",
    body: "Reach out to Andy (project owner) in the daily sync. For urgent issues outside sync hours, email siddhantandy@gmail.com. File database corruption under 'urgent'; UI glitches under 'normal'.",
  },
];

export default function HelpSection() {
  useAdminPageTitle("Help");
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-2">Admin Help</h1>
      <p className="text-gray-600 mb-6">
        Short how-to answers for the most common admin tasks. Each card answers one question.
      </p>
      <div className="space-y-4">
        {SECTIONS.map((s) => (
          <Card key={s.title}>
            <h2 className="font-semibold mb-2">{s.title}</h2>
            <p className="text-gray-700">{s.body}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
