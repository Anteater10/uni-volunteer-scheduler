import React from "react";

const ROLE_CLASS = {
  admin: "bg-purple-100 text-purple-800",
  organizer: "bg-blue-100 text-blue-800",
  participant: "bg-gray-100 text-gray-700",
};

function capitalize(s) {
  if (!s || typeof s !== "string") return "";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function RoleBadge({ role, className = "" }) {
  const cls = ROLE_CLASS[role] || ROLE_CLASS.participant;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls} ${className}`}
    >
      {capitalize(role)}
    </span>
  );
}
