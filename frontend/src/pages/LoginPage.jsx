import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../state/useAuth";

export default function LoginPage() {
  const nav = useNavigate();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      await login(email.trim(), password);
      nav("/admin");
    } catch (e2) {
      setErr(e2?.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex bg-white overflow-hidden">
      {/* ---- Left: branded hero panel ---- */}
      <div className="relative hidden lg:flex lg:w-1/2 xl:w-3/5 flex-col justify-between p-12 xl:p-16 text-white overflow-hidden bg-gradient-to-br from-blue-600 via-indigo-700 to-indigo-900">
        {/* decorative blobs */}
        <div
          aria-hidden="true"
          className="absolute -top-24 -left-24 h-96 w-96 rounded-full bg-blue-400/30 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute top-1/3 -right-32 h-[28rem] w-[28rem] rounded-full bg-indigo-400/30 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute -bottom-32 left-1/4 h-96 w-96 rounded-full bg-sky-400/20 blur-3xl"
        />
        {/* subtle grid overlay */}
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-[0.08]"
          style={{
            backgroundImage:
              "linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)",
            backgroundSize: "56px 56px",
          }}
        />

        {/* top — brand mark */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur ring-1 ring-white/25">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-6 w-6"
              aria-hidden="true"
            >
              <rect x="3" y="4" width="18" height="18" rx="2" />
              <path d="M16 2v4M8 2v4M3 10h18" />
            </svg>
          </div>
          <span className="text-lg font-semibold tracking-tight">
            Volunteer Scheduler
          </span>
        </div>

        {/* middle — pitch */}
        <div className="relative z-10 max-w-xl">
          <h2 className="text-5xl xl:text-6xl font-bold leading-[1.05] tracking-tight">
            Run volunteer events without the spreadsheet chaos.
          </h2>
          <p className="mt-6 text-lg xl:text-xl text-blue-100 leading-relaxed">
            Plan modules, publish signups, track rosters, and check volunteers
            in — all in one place. Built for UCSB SciTrek organisers.
          </p>

          <ul className="mt-10 space-y-4 text-base xl:text-lg">
            {[
              "One roster, shared across admins and organisers",
              "QR check-in with live attendance",
              "CSV imports for modules and schools",
            ].map((item) => (
              <li key={item} className="flex items-start gap-3">
                <span className="mt-1 inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-white/15 ring-1 ring-white/30">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-3.5 w-3.5"
                    aria-hidden="true"
                  >
                    <path d="M5 12l5 5L20 7" />
                  </svg>
                </span>
                <span className="text-blue-50">{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* bottom — footer */}
        <div className="relative z-10 text-sm text-blue-200">
          © {new Date().getFullYear()} UCSB SciTrek · Volunteer Scheduler
        </div>
      </div>

      {/* ---- Right: sign-in panel ---- */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 sm:px-12 bg-gradient-to-br from-slate-50 via-white to-blue-50/40 overflow-y-auto">
        <div className="w-full max-w-md">
          {/* mobile brand (only when left panel hidden) */}
          <div className="lg:hidden flex items-center gap-3 mb-10">
            <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-md">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-6 w-6"
                aria-hidden="true"
              >
                <rect x="3" y="4" width="18" height="18" rx="2" />
                <path d="M16 2v4M8 2v4M3 10h18" />
              </svg>
            </div>
            <span className="text-lg font-semibold tracking-tight text-gray-900">
              Volunteer Scheduler
            </span>
          </div>

          <div className="mb-8">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900">
              Welcome back
            </h1>
            <p className="mt-2 text-base text-gray-600">
              Sign in to manage events, volunteers, and rosters.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="login-email"
                className="block text-sm font-medium text-gray-800 mb-1.5"
              >
                Email
              </label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                placeholder="you@ucsb.edu"
                className="w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-base shadow-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
              />
            </div>
            <div>
              <label
                htmlFor="login-password"
                className="block text-sm font-medium text-gray-800 mb-1.5"
              >
                Password
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                placeholder="••••••••"
                className="w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-base shadow-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
              />
            </div>

            {err && (
              <div
                role="alert"
                className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800"
              >
                {err}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold py-3 px-4 shadow-md hover:shadow-lg transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-gray-500">
            For authorised organisers and administrators only.
          </p>
        </div>
      </div>
    </div>
  );
}
