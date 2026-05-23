// Settings section that surfaces the copilot's cross-session profile blob
// (Phase 34-08). Fetches GET /api/v1/copilot/profile on mount, renders the
// stored text + last-updated timestamp, and exposes a "Forget what you know
// about me" affordance that gates a DELETE behind a confirmation modal.
import React, { useCallback, useEffect, useState } from "react";

import { Button, Card, Label, Modal } from "../components/ui";
import { getProfile, deleteProfile } from "./api";

function formatTimestamp(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function CopilotMemorySettings() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProfile();
      setProfile(data);
    } catch (e) {
      setError(e?.message || "Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const onForgetClick = () => setConfirmOpen(true);
  const onCancel = () => setConfirmOpen(false);

  const onConfirmDelete = async () => {
    setDeleting(true);
    try {
      await deleteProfile();
      setConfirmOpen(false);
      await fetchProfile();
    } catch (e) {
      setError(e?.message || "Failed to clear profile");
    } finally {
      setDeleting(false);
    }
  };

  const isEmpty =
    !profile || !profile.profile_text || profile.profile_text.trim() === "";

  return (
    <Card>
      <div className="space-y-3">
        <div>
          <Label>What the copilot has learned about you</Label>
        </div>

        {loading ? (
          <p className="text-sm text-zinc-500">Loading profile…</p>
        ) : error ? (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        ) : isEmpty ? (
          <p className="text-sm text-zinc-600">
            The copilot hasn&apos;t learned anything stable about you yet.
            After a few sessions, useful context will appear here.
          </p>
        ) : (
          <div className="space-y-2">
            <pre className="text-sm whitespace-pre-wrap bg-zinc-50 p-3 rounded border border-zinc-200 overflow-x-auto">
              {profile.profile_text}
            </pre>
            {profile.updated_at && (
              <p className="text-xs text-zinc-500">
                Last updated: {formatTimestamp(profile.updated_at)}
              </p>
            )}
          </div>
        )}

        <div>
          <Button
            variant="danger"
            onClick={onForgetClick}
            disabled={loading || isEmpty}
          >
            Forget what you know about me
          </Button>
        </div>
      </div>

      <Modal
        open={confirmOpen}
        onClose={onCancel}
        title="Forget profile?"
      >
        <p className="text-sm text-zinc-700">
          This will permanently clear what the copilot has learned about you.
          New sessions will start fresh.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={deleting}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={onConfirmDelete}
            disabled={deleting}
          >
            {deleting ? "Clearing…" : "Forget"}
          </Button>
        </div>
      </Modal>
    </Card>
  );
}
