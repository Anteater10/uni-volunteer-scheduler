// K10 — the page must stop offering work that has already happened.
//
// The server now refuses a booking for a finished orientation or a finished
// shift (422 SESSION_ENDED) and marks `has_ended` on everything it returns.
// A live Sign-up button on top of that is the same bug wearing a different
// hat: the volunteer fills in the form and gets an error for their trouble.

import React from "react";
import { render, screen, within } from "@testing-library/react";
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
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("../../lib/calendar", () => ({
  downloadIcs: vi.fn(),
  buildGoogleCalendarUrl: vi.fn(() => "https://calendar.example/"),
}));

import api from "../../lib/api";
import EventDetailPage from "../public/EventDetailPage";

const ENDED_SLOT = {
  id: "slot-past",
  slot_type: "orientation",
  date: "2026-04-25",
  start_time: "2026-04-25T09:00:00",
  end_time: "2026-04-25T11:00:00",
  location: "Room 1",
  capacity: 10,
  filled: 3,
  has_ended: true,
};

const LIVE_SLOT = {
  id: "slot-future",
  slot_type: "orientation",
  date: "2026-04-26",
  start_time: "2026-04-26T09:00:00",
  end_time: "2026-04-26T11:00:00",
  location: "Room 2",
  capacity: 10,
  filled: 3,
  has_ended: false,
};

// Full AND over. "Already happened" has to win: a waitlist for a class that
// is finished is a queue for nothing.
const ENDED_AND_FULL_SHIFT = {
  id: "shift-past",
  name: "Mon 9:00-11:00",
  sort_order: 0,
  capacity: 4,
  filled: 4,
  has_ended: true,
  sessions: [
    {
      id: "sess-past",
      name: "Period 1",
      sort_order: 0,
      date: "2026-04-25",
      start_time: "2026-04-25T09:00:00",
      end_time: "2026-04-25T11:00:00",
      location: "Room 1",
      has_ended: true,
    },
  ],
};

// One session gone, one still to staff — the volunteer is still needed.
const PART_DONE_SHIFT = {
  id: "shift-partial",
  name: "Tue 9:00-11:00",
  sort_order: 1,
  capacity: 4,
  filled: 1,
  has_ended: false,
  sessions: [
    {
      id: "sess-gone",
      name: "Period 1",
      sort_order: 0,
      date: "2026-04-25",
      start_time: "2026-04-25T09:00:00",
      end_time: "2026-04-25T11:00:00",
      location: "Room 1",
      has_ended: true,
    },
    {
      id: "sess-left",
      name: "Period 2",
      sort_order: 1,
      date: "2026-04-26",
      start_time: "2026-04-26T09:00:00",
      end_time: "2026-04-26T11:00:00",
      location: "Room 1",
      has_ended: false,
    },
  ],
};

const MOCK_EVENT = {
  id: "evt-ended",
  slug: "ended-test",
  title: "Ended Test Event",
  quarter: "spring",
  year: 2026,
  week_number: 5,
  school: "Test HS",
  module_slug: "test",
  start_date: "2026-04-25",
  end_date: "2026-04-26",
  slots: [ENDED_SLOT, LIVE_SLOT],
  shifts: [ENDED_AND_FULL_SHIFT, PART_DONE_SHIFT],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/events/evt-ended"]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventDetailPage — units that have already happened (K10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getEvent.mockResolvedValue(MOCK_EVENT);
    api.public.getFormSchema.mockResolvedValue({ schema: [] });
    api.public.orientationCheck.mockResolvedValue({ has_credit: true });
  });

  it("disables the button on a shift that is over", async () => {
    renderPage();
    await screen.findByText("Ended Test Event");

    const card = screen.getByTestId(`shift-${ENDED_AND_FULL_SHIFT.id}`);
    const button = within(card).getByRole("button", { name: /ended/i });
    expect(button).toBeDisabled();
  });

  it("offers no waitlist on a shift that is both full and over", async () => {
    renderPage();
    await screen.findByText("Ended Test Event");

    const card = screen.getByTestId(`shift-${ENDED_AND_FULL_SHIFT.id}`);
    expect(within(card).queryByRole("button", { name: /waitlist/i })).toBeNull();
    expect(within(card).getByText(/already happened/i)).toBeInTheDocument();
  });

  it("leaves a shift with a session still to come bookable", async () => {
    renderPage();
    await screen.findByText("Ended Test Event");

    const card = screen.getByTestId(`shift-${PART_DONE_SHIFT.id}`);
    const button = within(card).getByRole("button", { name: /^sign up$/i });
    expect(button).toBeEnabled();
  });

  it("still offers the orientation session that has not happened yet", async () => {
    renderPage();
    await screen.findByText("Ended Test Event");

    // Both the desktop table and the mobile card render at once in jsdom, so
    // the live slot contributes more than one enabled button — every one of
    // them must be live, and none of them may belong to the finished slot.
    const live = screen.getAllByRole("button", { name: /^sign up$/i });
    expect(live.length).toBeGreaterThan(0);
    live.forEach((b) => expect(b).toBeEnabled());

    const ended = screen.getAllByRole("button", { name: /^ended$/i });
    ended.forEach((b) => expect(b).toBeDisabled());
  });
});
