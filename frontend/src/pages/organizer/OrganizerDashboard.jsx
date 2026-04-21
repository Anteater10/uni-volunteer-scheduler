import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";

function fmtTimeRange(startIso, endIso) {
  if (!startIso) return "—";
  try {
    const start = new Date(startIso);
    const end = endIso ? new Date(endIso) : null;
    const sameDay =
      end &&
      start.getFullYear() === end.getFullYear() &&
      start.getMonth() === end.getMonth() &&
      start.getDate() === end.getDate();
    const dateStr = start.toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    const startTime = start.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
    if (!end) return `${dateStr} · ${startTime}`;
    const endTime = end.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
    if (sameDay) return `${dateStr} · ${startTime} – ${endTime}`;
    const endDateStr = end.toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    return `${dateStr} ${startTime} → ${endDateStr} ${endTime}`;
  } catch {
    return startIso;
  }
}

function isToday(iso) {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

const SCOPES = [
  { id: "today", label: "Today" },
  { id: "upcoming", label: "Upcoming" },
  { id: "past", label: "Past" },
];

export default function OrganizerDashboard() {
  const [scope, setScope] = useState("today");

  const q = useQuery({
    queryKey: ["organizerEvents"],
    queryFn: () => api.events.list(),
    refetchOnWindowFocus: true,
  });

  const events = q.data || [];

  const filtered = useMemo(() => {
    const now = Date.now();
    return events
      .filter((e) => {
        if (scope === "today") {
          return isToday(e.start_date) || isToday(e.end_date);
        }
        if (scope === "upcoming") {
          return new Date(e.end_date).getTime() >= now && !isToday(e.end_date);
        }
        if (scope === "past") {
          return new Date(e.end_date).getTime() < now;
        }
        return true;
      })
      .sort((a, b) => {
        const aStart = new Date(a.start_date).getTime();
        const bStart = new Date(b.start_date).getTime();
        return scope === "past" ? bStart - aStart : aStart - bStart;
      });
  }, [events, scope]);

  const todayCount = useMemo(
    () => events.filter((e) => isToday(e.start_date) || isToday(e.end_date)).length,
    [events],
  );

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-gray-900">Organizer</h1>
        <p className="text-sm text-gray-600 mt-1">
          {todayCount > 0
            ? `${todayCount} event${todayCount === 1 ? "" : "s"} today. Tap an event to open its roster.`
            : "No events today. Switch tabs to see upcoming or past events."}
        </p>
      </header>

      <div
        role="tablist"
        aria-label="Event scope"
        className="flex gap-1 rounded-lg bg-gray-100 p-1"
      >
        {SCOPES.map((s) => {
          const active = scope === s.id;
          return (
            <button
              key={s.id}
              role="tab"
              aria-selected={active}
              onClick={() => setScope(s.id)}
              className={
                "flex-1 min-h-[44px] text-sm font-medium rounded-md transition " +
                (active
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-600 hover:text-gray-900")
              }
            >
              {s.label}
            </button>
          );
        })}
      </div>

      {q.isPending ? (
        <p className="text-sm text-gray-500">Loading events…</p>
      ) : q.error ? (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          Couldn't load events: {q.error.message}{" "}
          <button onClick={() => q.refetch()} className="underline ml-2 min-h-[44px]">
            Retry
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-600 text-center">
          {scope === "today"
            ? "No events scheduled for today."
            : scope === "upcoming"
              ? "No upcoming events."
              : "No past events."}
        </div>
      ) : (
        <ul className="space-y-3">
          {filtered.map((e) => (
            <li
              key={e.id}
              className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-base font-semibold text-gray-900 leading-snug">
                  {e.title || "(untitled event)"}
                </h2>
                {isToday(e.start_date) || isToday(e.end_date) ? (
                  <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                    Today
                  </span>
                ) : null}
              </div>
              <p className="text-sm text-gray-600 mt-1">
                {fmtTimeRange(e.start_date, e.end_date)}
              </p>
              {e.location ? (
                <p className="text-sm text-gray-600 mt-0.5">{e.location}</p>
              ) : null}
              <div className="mt-3 flex flex-col sm:flex-row gap-2">
                <Link
                  to={`/organizer/events/${e.id}/roster`}
                  className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  Open roster
                </Link>
                <Link
                  to={`/admin/events/${e.id}`}
                  className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  View details
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
