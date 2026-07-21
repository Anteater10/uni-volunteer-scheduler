import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
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
      <div className="relative hidden lg:flex lg:w-1/2 xl:w-3/5 flex-col justify-between p-12 xl:p-16 text-white overflow-hidden bg-gradient-to-br from-sky-500 via-sky-700 to-sky-900">
        {/* decorative blobs — SciTrek blue field with one warm test-tube accent */}
        <div
          aria-hidden="true"
          className="absolute -top-24 -left-24 h-96 w-96 rounded-full bg-sky-300/30 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute top-1/3 -right-32 h-[28rem] w-[28rem] rounded-full bg-sky-400/25 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute -bottom-32 left-1/4 h-96 w-96 rounded-full bg-orange-400/20 blur-3xl"
        />
        {/* subtle grid overlay */}
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)",
            backgroundSize: "56px 56px",
          }}
        />

        {/* top — brand mark (logo needs a light chip to read on the blue field) */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="inline-flex items-center rounded-xl bg-white px-4 py-2.5 shadow-lg ring-1 ring-black/5">
            <img
              src="/scitrek_logo.png"
              alt="SciTrek"
              className="h-8 w-auto"
            />
          </div>
          <span className="text-base font-medium tracking-tight text-sky-50">
            Volunteer Scheduler
          </span>
        </div>

        {/* middle — pitch */}
        <div className="relative z-10 max-w-xl animate-fade-up">
          <span className="inline-block h-1.5 w-14 rounded-full bg-orange-400" />
          <h2 className="mt-6 text-4xl xl:text-5xl font-bold leading-[1.1] tracking-tight">
            Run volunteer events without the spreadsheet chaos.
          </h2>
          <p className="mt-5 text-lg text-sky-100 leading-relaxed">
            Plan modules, publish signups, track rosters, and check volunteers
            in — all in one place. Built for UCSB SciTrek organisers.
          </p>

          <ul className="mt-9 space-y-4 text-base">
            {[
              "One roster, shared across admins and organisers",
              "QR check-in with live attendance",
              "CSV imports for modules and schools",
            ].map((item) => (
              <li key={item} className="flex items-start gap-3">
                <span className="mt-0.5 inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-orange-500 shadow-sm">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-3.5 w-3.5 text-white"
                    aria-hidden="true"
                  >
                    <path d="M5 12l5 5L20 7" />
                  </svg>
                </span>
                <span className="text-sky-50">{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* bottom — footer */}
        <div className="relative z-10 text-sm text-sky-200/90">
          © {new Date().getFullYear()} UCSB SciTrek · Volunteer Scheduler
        </div>
      </div>

      {/* ---- Right: sign-in panel ---- */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 sm:px-12 bg-gradient-to-br from-slate-50 via-white to-sky-50/50 overflow-y-auto">
        <div className="w-full max-w-md animate-fade-up">
          {/* brand — full logo reads perfectly on the light panel */}
          <div className="mb-10 flex justify-center lg:justify-start">
            <img
              src="/scitrek_logo.png"
              alt="SciTrek"
              className="h-12 w-auto"
            />
          </div>

          <div className="mb-8">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900">
              Welcome back
            </h1>
            <p className="mt-3 text-base text-gray-600">
              Sign in to manage events, volunteers, and rosters.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="login-email"
                className="block text-sm font-medium text-gray-700 mb-1.5"
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
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-base shadow-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-sky-600 transition"
              />
            </div>
            <div>
              <label
                htmlFor="login-password"
                className="block text-sm font-medium text-gray-700 mb-1.5"
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
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-base shadow-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-sky-600 transition"
              />
            </div>

            {err && (
              <div
                role="alert"
                className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800"
              >
                {err}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-sky-700 hover:bg-sky-800 text-white font-semibold text-base py-3 px-4 shadow-md hover:shadow-lg transition disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-sky-600 focus:ring-offset-2"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <Link
            to="/volunteer"
            className="mt-4 block w-full rounded-lg border border-gray-300 bg-white text-center text-base font-semibold text-gray-700 py-2.5 hover:bg-gray-50 hover:border-gray-400 transition"
          >
            Browse events →
          </Link>

          <p className="mt-8 text-center text-sm text-gray-500">
            For authorised organisers and administrators only.
          </p>
        </div>
      </div>
    </div>
  );
}
