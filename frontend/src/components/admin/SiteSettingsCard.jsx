// src/components/admin/SiteSettingsCard.jsx
//
// Phase 29 (HIDE-01) — minimal admin settings surface with the
// "Hide past events from public browse" toggle. Fetches + patches the
// singleton ``site_settings`` row via ``api.admin.siteSettings``.
//
// Intentionally small: we reuse the existing Card primitive and keep
// everything on the Overview page so admins don't need to navigate to a
// new Settings route to flip this single v1.3 switch. If Phase 30+ grows
// this surface, promote it to its own /admin/settings route.

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Card } from "../ui";
import { toast } from "../../state/toast";

export default function SiteSettingsCard() {
  const qc = useQueryClient();
  // Defensive: tests may mock `api.admin` without the siteSettings subtree.
  // When unavailable we render the card with defaults and a disabled toggle.
  const api_ok =
    typeof api?.admin?.siteSettings?.get === "function" &&
    typeof api?.admin?.siteSettings?.update === "function";
  const q = useQuery({
    queryKey: ["adminSiteSettings"],
    queryFn: () => api.admin.siteSettings.get(),
    enabled: api_ok,
  });

  const m = useMutation({
    mutationFn: (patch) =>
      api_ok ? api.admin.siteSettings.update(patch) : Promise.resolve({}),
    onSuccess: (row) => {
      qc.setQueryData(["adminSiteSettings"], row);
      toast.success("Settings updated.");
    },
    onError: (err) => toast.error(err?.message || "Failed to update settings."),
  });

  const hidePast = q.data?.hide_past_events_from_public ?? true;

  return (
    <Card data-testid="site-settings-card">
      <h3 className="text-sm font-medium text-gray-700">Site settings</h3>
      <div className="mt-3 flex items-start justify-between gap-4">
        <div className="text-sm text-gray-700">
          <div className="font-medium">Hide past events from public browse</div>
          <div className="text-gray-500 text-xs mt-0.5">
            When on, volunteers only see events whose last slot hasn't ended
            yet. Admins always see everything.
          </div>
        </div>
        <label className="inline-flex cursor-pointer items-center">
          <input
            type="checkbox"
            className="peer sr-only"
            checked={hidePast}
            disabled={!api_ok || q.isPending || m.isPending}
            onChange={(e) =>
              m.mutate({ hide_past_events_from_public: e.target.checked })
            }
            aria-label="Hide past events from public browse"
            data-testid="hide-past-toggle"
          />
          <span
            className={
              "relative inline-block h-6 w-11 rounded-full transition-colors " +
              (hidePast ? "bg-blue-600" : "bg-gray-300")
            }
          >
            <span
              className={
                "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform " +
                (hidePast ? "translate-x-5" : "translate-x-0")
              }
            />
          </span>
        </label>
      </div>
    </Card>
  );
}
