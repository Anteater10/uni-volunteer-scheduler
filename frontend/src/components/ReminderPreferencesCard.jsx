// Phase 24 — Email reminder preferences card.
//
// Lives inside the token-gated manage-my-signup page. Fetches the
// volunteer's preferences, renders a single toggle for email reminders,
// and PUTs changes on toggle.
//
// The toggle is the minimum REM-03 surface; SMS opt-in lands in Phase 27.

import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "../state/toast";
import { Card } from "./ui";

export default function ReminderPreferencesCard({ manageToken }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!manageToken) {
      setLoading(false);
      return;
    }
    (async () => {
      setLoading(true);
      setError("");
      try {
        const pref = await api.public.getPreferences(manageToken);
        if (!cancelled) setEnabled(!!pref.email_reminders_enabled);
      } catch (e) {
        if (!cancelled) setError(e?.message || "Could not load preferences.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [manageToken]);

  async function handleToggle() {
    if (saving) return;
    const next = !enabled;
    // Optimistic
    setEnabled(next);
    setSaving(true);
    try {
      await api.public.updatePreferences(manageToken, {
        email_reminders_enabled: next,
      });
      toast.success(
        next
          ? "Reminder emails turned on."
          : "You won't get reminder emails anymore."
      );
    } catch (e) {
      // Revert
      setEnabled(!next);
      toast.error(e?.message || "Could not update preferences.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <Card className="p-4" data-testid="reminder-prefs-card">
        <p className="text-sm text-gray-500">Loading reminder preferences…</p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-4" data-testid="reminder-prefs-card">
        <p className="text-sm text-gray-600">
          Couldn't load reminder preferences. You'll still receive them by default.
        </p>
      </Card>
    );
  }

  return (
    <Card className="p-4" data-testid="reminder-prefs-card">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">
        Email reminder preferences
      </h3>
      <p className="text-sm text-gray-600 mb-3">
        We send a kickoff email Monday morning, plus 24-hour and 2-hour nudges
        before your slot. Turn them off here if you'd rather not get them.
      </p>
      <label className="flex items-center gap-3 cursor-pointer select-none">
        <span className="relative inline-block w-11 h-6">
          <input
            type="checkbox"
            className="peer sr-only"
            checked={enabled}
            onChange={handleToggle}
            disabled={saving}
            aria-label="Send me reminder emails"
          />
          <span
            aria-hidden="true"
            className="block w-11 h-6 bg-gray-300 peer-checked:bg-blue-600 rounded-full transition-colors"
          />
          <span
            aria-hidden="true"
            className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform peer-checked:translate-x-5"
          />
        </span>
        <span className="text-sm text-gray-900">
          {enabled ? "Send me reminder emails" : "Reminders off"}
        </span>
      </label>
    </Card>
  );
}
