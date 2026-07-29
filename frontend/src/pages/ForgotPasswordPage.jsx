import React, { useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";

/**
 * PR #51 — staff self-service password reset.
 *
 * Submitting always lands on the same "check your email" state: the backend
 * answers 202 whether or not the address has an account, and this page must
 * not undo that by wording success differently per address.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setError(err?.message || "Something went wrong. Try again in a minute.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="mx-auto max-w-md p-8">
        <h1 className="text-2xl font-semibold">Check your email</h1>
        <p className="text-sm text-gray-600 mt-2">
          If <span className="font-medium">{email.trim()}</span> has a staff
          account, a reset link is on its way. It expires in an hour — check
          your spam folder if it doesn't show up.
        </p>
        <Link to="/login" className="mt-4 inline-block text-blue-600 underline">
          Back to login
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md p-8">
      <h1 className="text-2xl font-semibold">Reset your password</h1>
      <p className="text-sm text-gray-600 mt-1">
        Enter your staff email and we'll send a link to choose a new password.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4 mt-6">
        <div>
          <label htmlFor="fp-email" className="block text-sm font-medium mb-1">
            Email
          </label>
          <input
            id="fp-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@ucsb.edu"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            required
          />
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800"
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-sky-700 hover:bg-sky-800 text-white font-semibold py-2.5 px-4 transition disabled:opacity-60"
        >
          {busy ? "Sending…" : "Email me a reset link"}
        </button>

        <Link
          to="/login"
          className="block text-center text-sm font-medium text-sky-700 hover:underline"
        >
          Back to login
        </Link>
      </form>
    </div>
  );
}
