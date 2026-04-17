// Phase 25 — EventDetailPage.waitlist.test.jsx
//
// Verifies WAIT-01 behavior: when the public signup response contains a
// signup with status "waitlisted", the page surfaces a toast with the
// 1-indexed FIFO position.

import React from "react";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getEvent: vi.fn(),
      getFormSchema: vi.fn(),
      createSignup: vi.fn(),
      orientationStatus: vi.fn(),
      orientationCheck: vi.fn(),
    },
  },
}));

vi.mock("../../state/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock("../../lib/calendar", () => ({
  downloadIcs: vi.fn(),
}));

import api from "../../lib/api";
import { toast } from "../../state/toast";
import EventDetailPage from "../public/EventDetailPage";

const WAITLISTABLE_SLOT = {
  id: "slot-wl",
  slot_type: "orientation",
  date: "2026-04-25",
  start_time: "2026-04-25T09:00:00",
  end_time: "2026-04-25T11:00:00",
  location: "Room 1",
  capacity: 10,
  filled: 3,
};

const MOCK_EVENT = {
  id: "evt-wl",
  slug: "waitlist-test",
  title: "Waitlist Test Event",
  quarter: "spring",
  year: 2026,
  week_number: 5,
  school: "Test HS",
  module_slug: "test",
  start_date: "2026-04-25",
  end_date: "2026-04-26",
  slots: [WAITLISTABLE_SLOT],
};

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/events/evt-wl"]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
          <Route path="/events" element={<div>Events list page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventDetailPage waitlist UX (Phase 25)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getEvent.mockResolvedValue(MOCK_EVENT);
    api.public.getFormSchema.mockResolvedValue({ schema: [] });
    api.public.orientationCheck.mockResolvedValue({ has_credit: true });
  });

  it("toasts the waitlist position when the signup comes back waitlisted", async () => {
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "v-1",
      signup_ids: ["sig-wl"],
      magic_link_sent: true,
      signups: [
        { signup_id: "sig-wl", status: "waitlisted", position: 2 },
      ],
    });

    const { container } = renderPage();
    await screen.findByText("Waitlist Test Event");

    const signUpButtons = await screen.findAllByRole("button", {
      name: /^sign up$/i,
    });
    fireEvent.click(signUpButtons[0]);

    await screen.findByLabelText(/^first name$/i);
    await userEvent.type(screen.getByLabelText(/^first name$/i), "Ada");
    await userEvent.type(screen.getByLabelText(/^last name$/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/^email$/i), "ada@example.com");
    await userEvent.type(screen.getByLabelText(/^phone$/i), "(213) 867-5309");

    const submit = container.querySelector('form button[type="submit"]');
    await act(async () => {
      fireEvent.click(submit);
    });

    await waitFor(() => {
      const called =
        toast.info.mock.calls.some((args) =>
          String(args[0]).match(/waitlist.*position 2/i),
        ) ||
        toast.success.mock.calls.some((args) =>
          String(args[0]).match(/waitlist.*position 2/i),
        );
      expect(called).toBe(true);
    });
  });

  it("does not show waitlist toast for confirmed signups", async () => {
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "v-1",
      signup_ids: ["sig-ok"],
      magic_link_sent: true,
      signups: [{ signup_id: "sig-ok", status: "pending", position: null }],
    });

    const { container } = renderPage();
    await screen.findByText("Waitlist Test Event");

    const signUpButtons = await screen.findAllByRole("button", {
      name: /^sign up$/i,
    });
    fireEvent.click(signUpButtons[0]);

    await screen.findByLabelText(/^first name$/i);
    await userEvent.type(screen.getByLabelText(/^first name$/i), "Bob");
    await userEvent.type(screen.getByLabelText(/^last name$/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^email$/i), "bob@example.com");
    await userEvent.type(screen.getByLabelText(/^phone$/i), "(213) 867-5309");

    const submit = container.querySelector('form button[type="submit"]');
    await act(async () => {
      fireEvent.click(submit);
    });

    await waitFor(() => {
      expect(api.public.createSignup).toHaveBeenCalled();
    });

    // Neither toast variant was called with a waitlist message.
    const allToastCalls = [
      ...toast.info.mock.calls,
      ...toast.success.mock.calls,
    ];
    const waitlistCalled = allToastCalls.some((args) =>
      String(args[0]).match(/waitlist/i),
    );
    expect(waitlistCalled).toBe(false);
  });
});
