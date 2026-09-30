// Spam-clicking Sign up must send one signup, not several.
import React from "react";
import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getEvent: vi.fn(),
      getFormSchema: vi.fn(async () => ({ schema: [] })),
      createSignup: vi.fn(),
      orientationCheck: vi.fn(),
    },
  },
}));
vi.mock("../../state/toast", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("../../lib/calendar", () => ({ downloadIcs: vi.fn(), buildGoogleCalendarUrl: vi.fn() }));

import api from "../../lib/api";
import EventDetailPage from "../public/EventDetailPage";

const EVENT = {
  id: "evt-1", title: "Race", start_date: "2026-10-20T07:00:00Z", end_date: "2026-10-22T07:00:00Z",
  slots: [{ id: "o1", slot_type: "orientation", date: "2026-10-06", start_time: "2026-10-06T23:00:00Z", end_time: "2026-10-07T01:00:00Z", capacity: 5, filled: 0 }],
  shifts: [{ id: "sh1", name: "Shift", capacity: 5, filled: 0, sessions: [] }],
};

function renderPage() {
  api.public.getEvent.mockResolvedValue(EVENT);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/events/evt-1"]}>
        <Routes><Route path="/events/:eventId" element={<EventDetailPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function fillAndPick(pickShift) {
  const table = screen.getByRole("table");
  fireEvent.click(within(table).getByRole("button", { name: "Sign up" }));
  if (pickShift) fireEvent.click(within(screen.getByTestId("shift-sh1")).getByRole("button"));
  for (const [id, value] of Object.entries({ first_name: "A", last_name: "B", email: "a@x.com", phone: "8055551234" })) {
    fireEvent.change(document.getElementById(id), { target: { value } });
  }
}

beforeEach(() => vi.clearAllMocks());

it("sends one signup when Sign up is clicked five times fast", async () => {
  let resolve;
  api.public.createSignup.mockReturnValue(new Promise((r) => { resolve = r; }));
  renderPage();
  await screen.findByRole("heading", { level: 1 });
  fillAndPick(false);
  const button = screen.getByTestId("signup-submit");
  for (let i = 0; i < 5; i++) fireEvent.click(button);
  await waitFor(() => expect(api.public.createSignup).toHaveBeenCalledTimes(1));
  // While submitting the form is taken off the page entirely.
  expect(screen.queryByTestId("signup-submit")).not.toBeInTheDocument();
  resolve({ signups: [] });
  await waitFor(() => expect(api.public.createSignup).toHaveBeenCalledTimes(1));
});

it("sends one signup when clicked fast during the orientation check", async () => {
  let resolveCheck;
  api.public.orientationCheck.mockReturnValue(new Promise((r) => { resolveCheck = r; }));
  api.public.createSignup.mockResolvedValue({ signups: [] });
  renderPage();
  await screen.findByRole("heading", { level: 1 });
  fillAndPick(true);
  // Untick the orientation so the shift-only check runs.
  fireEvent.click(within(screen.getByRole("table")).getByRole("button", { name: "Selected" }));
  const button = screen.getByTestId("signup-submit");
  for (let i = 0; i < 5; i++) fireEvent.click(button);
  resolveCheck({ has_credit: true });
  await waitFor(() => expect(api.public.createSignup).toHaveBeenCalled());
  expect(api.public.orientationCheck).toHaveBeenCalledTimes(1);
  expect(api.public.createSignup).toHaveBeenCalledTimes(1);
});
