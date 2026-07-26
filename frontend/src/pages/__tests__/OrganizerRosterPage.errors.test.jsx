// src/pages/__tests__/OrganizerRosterPage.errors.test.jsx
//
// The roster used to report every failure as "You appear to be offline — retry
// in 5s", with no retry control. A 403 (which organizers hit constantly before
// the event-access rule was fixed) and a deleted event both looked like a
// network blip, so the organizer had nothing to act on. These pin the three
// distinct outcomes.

import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
// Imported rather than taken from vitest's globals so this file lints clean;
// the config declares no test globals.
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../api/roster", () => ({
  fetchRoster: vi.fn(),
  checkInSignup: vi.fn(),
  undoCheckInSignup: vi.fn(),
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({ role: "organizer" }),
}));

import { fetchRoster } from "../../api/roster";
import OrganizerRosterPage from "../OrganizerRosterPage";

function failWith(status) {
  const err = new Error(`failed (${status})`);
  err.status = status;
  fetchRoster.mockRejectedValue(err);
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <OrganizerRosterPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OrganizerRosterPage — load failures", () => {
  beforeEach(() => vi.clearAllMocks());

  it("explains a 403 as a permission problem, not a connection problem", async () => {
    failWith(403);
    renderPage();

    expect(await screen.findByText(/don't have access/i)).toBeInTheDocument();
    expect(screen.queryByText(/offline/i)).not.toBeInTheDocument();
    // Retrying a permission denial just fails again.
    expect(
      screen.queryByRole("button", { name: /try again/i }),
    ).not.toBeInTheDocument();
  });

  it("says a 404 event is gone", async () => {
    failWith(404);
    renderPage();

    expect(await screen.findByText(/no longer exists/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /try again/i }),
    ).not.toBeInTheDocument();
  });

  it("offers a retry for an actual network failure", async () => {
    fetchRoster.mockRejectedValue(new Error("Network request failed"));
    renderPage();

    expect(await screen.findByText(/check your connection/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });
});
