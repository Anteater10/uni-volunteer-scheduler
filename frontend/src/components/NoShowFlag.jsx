// src/components/NoShowFlag.jsx
import React from "react";
import { Flag } from "lucide-react";

// Two separate broken commitments, not two missed days of one shift — the
// backend counts distinct bookings, so a volunteer who misses one Tue/Wed/Thu
// shift is at 1, not 3.
export const NO_SHOW_FLAG_THRESHOLD = 2;

export default function NoShowFlag({ count }) {
  if (!count || count < NO_SHOW_FLAG_THRESHOLD) return null;
  const label = `${count} no-shows in the last 12 months`;
  return (
    <span
      data-testid="no-show-flag"
      title={label}
      aria-label={label}
      role="img"
      className="ml-1.5 inline-flex align-middle text-red-600"
    >
      <Flag className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
    </span>
  );
}
