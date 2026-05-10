// Floating action button + drawer container.
//
// Visible only to admin and organizer roles when COPILOT_ENABLED.
// The flag is read from import.meta.env.VITE_COPILOT_ENABLED to mirror
// the backend's COPILOT_ENABLED feature flag.
import React, { useState } from "react";
import { Sparkles } from "lucide-react";
import { useAuth } from "../state/useAuth";
import CopilotDrawer from "./CopilotDrawer";

function isEnabled() {
  const raw = import.meta.env.VITE_COPILOT_ENABLED;
  return raw === "true" || raw === "1";
}

export default function CopilotFab() {
  const { role, isAuthed } = useAuth();
  const [open, setOpen] = useState(false);

  if (!isEnabled()) return null;
  if (!isAuthed) return null;
  if (role !== "admin" && role !== "organizer") return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open SciTrek Copilot"
        className="fixed bottom-6 right-6 z-30 w-14 h-14 rounded-full bg-indigo-600 text-white shadow-lg hover:bg-indigo-700 flex items-center justify-center"
      >
        <Sparkles className="w-6 h-6" />
      </button>
      <CopilotDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
