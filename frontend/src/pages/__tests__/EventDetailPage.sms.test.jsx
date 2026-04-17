// Phase 27 — EventDetailPage SMS opt-in checkbox tests.
//
// Verifies:
// - When `sms_enabled=false`, the SMS opt-in checkbox is NOT rendered.
// - When `sms_enabled=true`, the checkbox renders and checking it propagates
//   `sms_opt_in: true` into the createSignup payload.

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
      getConfig: vi.fn(),
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
import EventDetailPage from "../public/EventDetailPage";

const ORIENT_SLOT = {
  id: "slot-or-1",
  slot_type: "orientation",
  date: "2026-04-25",
  start_time: "2026-04-25T09:00:00",
  end_time: "2026-04-25T11:00:00",
  location: "Room 1",
  capacity: 10,
  filled: 3,
};

const MOCK_EVENT = {
  id: "evt-sms",
  slug: "sms-test",
  title: "SMS Test Event",
  quarter: "spring",
  year: 2026,
  week_number: 5,
  school: "Test HS",
  module_slug: "test",
  start_date: "2026-04-25",
  end_date: "2026-04-26",
  slots: [ORIENT_SLOT],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/events/evt-sms"]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventDetailPage SMS opt-in (Phase 27)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getEvent.mockResolvedValue(MOCK_EVENT);
    api.public.getFormSchema.mockResolvedValue({ schema: [] });
    api.public.orientationCheck.mockResolvedValue({ has_credit: true });
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "v-1",
      signup_ids: ["sig-1"],
      magic_link_sent: true,
      signups: [{ signup_id: "sig-1", status: "pending", position: null }],
    });
  });

  it("does NOT render the SMS opt-in checkbox when sms_enabled=false", async () => {
    api.public.getConfig.mockResolvedValue({ sms_enabled: false });
    renderPage();
    await screen.findByText("SMS Test Event");

    const signUpButtons = await screen.findAllByRole("button", {
      name: /^sign up$/i,
    });
    fireEvent.click(signUpButtons[0]);

    await screen.findByLabelText(/^first name$/i);
    // The SMS consent checkbox should not be present.
    expect(
      screen.queryByLabelText(/text me reminders/i),
    ).not.toBeInTheDocument();
  });

  it("renders the checkbox and sends sms_opt_in=true when flag on + checked", async () => {
    api.public.getConfig.mockResolvedValue({ sms_enabled: true });
    const { container } = renderPage();
    await screen.findByText("SMS Test Event");

    const signUpButtons = await screen.findAllByRole("button", {
      name: /^sign up$/i,
    });
    fireEvent.click(signUpButtons[0]);

    await screen.findByLabelText(/^first name$/i);
    const smsBox = await screen.findByLabelText(/text me reminders/i);
    expect(smsBox).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/^first name$/i), "Ada");
    await userEvent.type(screen.getByLabelText(/^last name$/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/^email$/i), "ada@example.com");
    await userEvent.type(screen.getByLabelText(/^phone$/i), "(213) 867-5309");
    fireEvent.click(smsBox);

    const submit = container.querySelector('form button[type="submit"]');
    await act(async () => {
      fireEvent.click(submit);
    });

    await waitFor(() => {
      expect(api.public.createSignup).toHaveBeenCalled();
    });
    const payload = api.public.createSignup.mock.calls[0][0];
    expect(payload.sms_opt_in).toBe(true);
  });
});
