import React, { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAuth } from "../state/useAuth";
import { toast } from "../state/toast";
import {
  PageHeader,
  Card,
  Button,
  Label,
  Input,
  FieldError,
} from "../components/ui";
import CopilotMemorySettings from "../copilot/CopilotMemorySettings";

// Section wrapper — a titled card with a one-line explanation, so each block
// says what it is for rather than presenting a bare row of inputs.
function SettingsSection({ title, hint, children }) {
  return (
    <section>
      <h2 className="text-base font-semibold text-[var(--color-fg-muted)] uppercase tracking-wide mb-3">
        {title}
      </h2>
      <Card>
        {hint ? (
          <p className="text-sm text-[var(--color-fg-muted)] mb-4">{hint}</p>
        ) : null}
        {children}
      </Card>
    </section>
  );
}

function ReadOnlyRow({ label, value }) {
  return (
    <div>
      <Label>{label}</Label>
      <p className="text-base">{value || "—"}</p>
    </div>
  );
}

/**
 * The editable half of the page.
 *
 * Split out and mounted with key={user.id} so its state initialises straight
 * from the loaded user. Seeding it in an effect instead would mean rendering
 * one frame of empty inputs, and re-syncing on every user change would fight
 * whatever the admin is currently typing.
 */
function ProfileForm({ user, reloadMe }) {
  const [name, setName] = useState(user.name || "");
  const [universityId, setUniversityId] = useState(user.university_id || "");
  const [notifyEmail, setNotifyEmail] = useState(user.notify_email !== false);
  const [err, setErr] = useState("");

  const saveM = useMutation({
    mutationFn: (body) => api.updateMe(body),
    onSuccess: async () => {
      // Refresh the cached user so the header and any name display update
      // without a reload.
      if (reloadMe) await reloadMe();
      toast.success("Settings saved.");
    },
    onError: (e) => setErr(e?.message || "Couldn't save your settings"),
  });

  const trimmedName = name.trim();
  const dirty =
    trimmedName !== (user.name || "") ||
    universityId.trim() !== (user.university_id || "") ||
    notifyEmail !== (user.notify_email !== false);

  function onSubmit(e) {
    e.preventDefault();
    setErr("");
    // Catches "" and "   " alike — a spaces-only name would otherwise save and
    // render as a blank row on every roster.
    if (!trimmedName) {
      setErr("Display name can't be empty.");
      return;
    }
    saveM.mutate({
      name: trimmedName,
      // Empty means "not set" — send null rather than "" so the column clears.
      university_id: universityId.trim() || null,
      notify_email: notifyEmail,
    });
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <SettingsSection
        title="Your details"
        hint="How your name appears to other staff on rosters and audit entries."
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="settings-name">Display name</Label>
            <Input
              id="settings-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              /* Deliberately not `required`: the native bubble would
                 pre-empt our own check, which also rejects a name that is
                 nothing but spaces. */
            />
          </div>
          <div>
            <Label htmlFor="settings-university-id">
              University ID <span className="font-normal">(optional)</span>
            </Label>
            <Input
              id="settings-university-id"
              value={universityId}
              onChange={(e) => setUniversityId(e.target.value)}
              placeholder="e.g. 1234567"
            />
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Notifications"
        hint="Reminder and roster emails sent to your staff address."
      >
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={notifyEmail}
            onChange={(e) => setNotifyEmail(e.target.checked)}
            className="mt-1 h-4 w-4 rounded border-[var(--color-border)] accent-[var(--color-brand)]"
          />
          <span className="text-sm">
            <span className="font-medium">Email me about my events</span>
            <span className="block text-[var(--color-fg-muted)]">
              Turning this off stops event email to you only. Volunteers still
              get their reminders.
            </span>
          </span>
        </label>
      </SettingsSection>

      <FieldError>{err}</FieldError>

      {/* Sticky-feeling save row: disabled until something actually changed,
          so the button doubles as an unsaved-changes indicator. */}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!dirty || saveM.isPending}>
          {saveM.isPending ? "Saving…" : "Save changes"}
        </Button>
        {dirty && !saveM.isPending ? (
          <span className="text-sm text-[var(--color-fg-muted)]">
            You have unsaved changes.
          </span>
        ) : null}
      </div>
    </form>
  );
}

/**
 * PR #51 — self-service password change. Its own form so a stray Enter in
 * the profile fields can never submit a password change (and vice versa).
 */
function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");

  const changeM = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Password changed. Other devices will need to log in again.");
    },
    onError: (e) => setErr(e?.message || "Couldn't change your password"),
  });

  function onSubmit(e) {
    e.preventDefault();
    setErr("");
    if (next.length < 8) {
      setErr("New password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      setErr("New passwords don't match.");
      return;
    }
    changeM.mutate();
  }

  return (
    <SettingsSection
      title="Password"
      hint="Changing your password signs out any other device using this account."
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <Label htmlFor="settings-current-password">Current password</Label>
          <Input
            id="settings-current-password"
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <Label htmlFor="settings-new-password">New password</Label>
            <Input
              id="settings-new-password"
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
            <p className="text-xs text-[var(--color-fg-muted)] mt-1">
              At least 8 characters.
            </p>
          </div>
          <div>
            <Label htmlFor="settings-confirm-password">
              Confirm new password
            </Label>
            <Input
              id="settings-confirm-password"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>
        </div>

        <FieldError>{err}</FieldError>

        <Button type="submit" disabled={changeM.isPending}>
          {changeM.isPending ? "Changing…" : "Change password"}
        </Button>
      </form>
    </SettingsSection>
  );
}

// Identity summary for the left rail — gives the wide layout an anchor and
// repeats the audit-identifying fields where the eye lands first.
function IdentityCard({ user }) {
  const initial = (user?.name || user?.email || "?").trim().charAt(0).toUpperCase();
  return (
    <Card>
      <div className="flex items-center gap-4">
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--color-brand)] to-sky-500 text-2xl font-semibold text-white shadow-sm">
          {initial}
        </span>
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">{user?.name || "—"}</p>
          <p className="truncate text-sm text-[var(--color-fg-muted)]">
            {user?.email}
          </p>
          <span className="mt-1 inline-flex items-center rounded-full bg-[var(--color-brand-soft)] px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-brand)]">
            {user?.role}
          </span>
        </div>
      </div>
    </Card>
  );
}

export default function UserSettingsPage() {
  const { user, reloadMe, logout } = useAuth();

  const copilotEnabled =
    import.meta.env.VITE_COPILOT_ENABLED === "true" ||
    import.meta.env.VITE_COPILOT_ENABLED === "1";

  return (
    <div className="w-full">
      <PageHeader
        title="Settings"
        subtitle="Your account details, password, and notification preferences."
      />

      <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-3 2xl:grid-cols-4">
        {/* Identity rail */}
        <div className="space-y-6 lg:col-span-1 2xl:col-span-1">
          {user ? <IdentityCard user={user} /> : null}

          <SettingsSection
            title="Account"
            hint="Only an admin can change these — they identify you in the audit log."
          >
            <div className="grid grid-cols-1 gap-4">
              <ReadOnlyRow label="Email" value={user?.email} />
              <ReadOnlyRow label="Role" value={user?.role} />
            </div>
          </SettingsSection>

          <SettingsSection title="Session">
            <Button variant="danger" onClick={logout}>
              Log out
            </Button>
          </SettingsSection>
        </div>

        {/* Main settings area */}
        <div className="lg:col-span-2 2xl:col-span-3">
          <div className="grid grid-cols-1 items-start gap-6 2xl:grid-cols-2">
            {/* The provider has already loaded /users/me to render the app
                shell, so this is only ever briefly null on a cold open. */}
            {user ? (
              <ProfileForm key={user.id} user={user} reloadMe={reloadMe} />
            ) : (
              <Card>
                <p className="text-sm text-[var(--color-fg-muted)]">
                  Loading your details…
                </p>
              </Card>
            )}

            <div className="space-y-6">
              <PasswordForm />
              {copilotEnabled ? <CopilotMemorySettings /> : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
