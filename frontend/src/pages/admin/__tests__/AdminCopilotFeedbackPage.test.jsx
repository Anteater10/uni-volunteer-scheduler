// Phase 35-01-E Task 19 — AdminCopilotFeedbackPage tests.
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

import AdminCopilotFeedbackPage from "../AdminCopilotFeedbackPage";

function makeFetch(routes) {
  return vi.fn(async (url) => {
    for (const key of Object.keys(routes)) {
      if (url.endsWith(key)) return routes[key]();
    }
    throw new Error(`unexpected ${url}`);
  });
}

describe("AdminCopilotFeedbackPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state before fetch resolves", () => {
    let resolveWeekly;
    let resolveBottom;
    const fetcher = makeFetch({
      "/admin/feedback/weekly": () =>
        new Promise((res) => {
          resolveWeekly = res;
        }),
      "/admin/feedback/bottom-messages": () =>
        new Promise((res) => {
          resolveBottom = res;
        }),
    });
    render(<AdminCopilotFeedbackPage fetcher={fetcher} />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
    // resolve to avoid open promises
    resolveWeekly({ ok: true, status: 200, json: async () => ({ weeks: [] }) });
    resolveBottom({
      ok: true,
      status: 200,
      json: async () => ({ messages: [] }),
    });
  });

  it("renders weekly table and bottom-quartile drill-down", async () => {
    const fetcher = makeFetch({
      "/admin/feedback/weekly": async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          weeks: [
            {
              iso_week: "2026-W21",
              thumbs_up_rate: 0.75,
              session_rating_avg: 4.2,
              n_messages: 8,
              n_sessions: 2,
            },
            {
              iso_week: "2026-W22",
              thumbs_up_rate: null,
              session_rating_avg: null,
              n_messages: 0,
              n_sessions: 0,
            },
          ],
        }),
      }),
      "/admin/feedback/bottom-messages": async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          messages: [
            {
              message_id: "m1",
              session_id: "s1",
              model_id: "gpt-4o-mini",
              rater_role: "admin",
              rated_at: "2026-05-23T10:00:00Z",
              comment: "wrong week",
              assistant_text: "Week 22 next.",
              prior_user_text: "What week are we in?",
            },
          ],
        }),
      }),
    });
    render(<AdminCopilotFeedbackPage fetcher={fetcher} />);
    await screen.findByText("2026-W21");
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("4.20")).toBeInTheDocument();
    expect(screen.getByText("2026-W22")).toBeInTheDocument();
    // expand drill-down
    fireEvent.click(screen.getByText(/wrong week/));
    expect(screen.getByText(/Week 22 next/)).toBeInTheDocument();
    expect(screen.getByText(/What week are we in/)).toBeInTheDocument();
    // collapse
    fireEvent.click(screen.getByText(/wrong week/));
    expect(screen.queryByText(/Week 22 next/)).not.toBeInTheDocument();
  });

  it("shows empty state when no weekly rows and no thumbs-down ratings", async () => {
    const fetcher = makeFetch({
      "/admin/feedback/weekly": async () => ({
        ok: true,
        status: 200,
        json: async () => ({ weeks: [] }),
      }),
      "/admin/feedback/bottom-messages": async () => ({
        ok: true,
        status: 200,
        json: async () => ({ messages: [] }),
      }),
    });
    render(<AdminCopilotFeedbackPage fetcher={fetcher} />);
    await screen.findByText(/No thumbs-down ratings yet/);
    expect(screen.getByText(/No ratings recorded yet/)).toBeInTheDocument();
  });

  it("renders error state when weekly fetch fails", async () => {
    const fetcher = makeFetch({
      "/admin/feedback/weekly": async () => ({
        ok: false,
        status: 500,
        json: async () => ({}),
      }),
      "/admin/feedback/bottom-messages": async () => ({
        ok: true,
        status: 200,
        json: async () => ({ messages: [] }),
      }),
    });
    render(<AdminCopilotFeedbackPage fetcher={fetcher} />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/weekly HTTP 500/),
    );
  });
});
