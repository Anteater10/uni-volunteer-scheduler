import React, { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../state/useAuth";

export default function SetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const { reloadMe } = useAuth();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (!token) {
    return (
      <div className="mx-auto max-w-md p-8">
        <h1 className="text-xl font-semibold mb-2">Invalid link</h1>
        <p className="text-sm text-gray-600">
          This page needs an invite token. Use the link from your invitation email.
        </p>
        <Link to="/login" className="mt-4 inline-block text-blue-600 underline">
          Go to login
        </Link>
      </div>
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await api.setPasswordFromInvite(token, password);
      if (reloadMe) await reloadMe();
      navigate("/admin", { replace: true });
    } catch (err) {
      setError(err?.message || "Failed to set password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md p-8">
      <h1 className="text-2xl font-semibold">Set your password</h1>
      <p className="text-sm text-gray-600 mt-1">
        Choose a password to finish setting up your account.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4 mt-6">
        <div>
          <label htmlFor="pw" className="block text-sm font-medium mb-1">
            Password
          </label>
          <input
            id="pw"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            required
            minLength={8}
          />
          <p className="text-xs text-gray-500 mt-1">At least 8 characters.</p>
        </div>
        <div>
          <label htmlFor="pw2" className="block text-sm font-medium mb-1">
            Confirm password
          </label>
          <input
            id="pw2"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            required
          />
        </div>

        {error && (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Setting…" : "Set password and sign in"}
        </button>
      </form>
    </div>
  );
}
