// src/pages/__tests__/EventDetailPage.test.jsx
//
// Component tests for EventDetailPage covering:
// - SignUpGenius-style button-based slot selection (current UI)
// - UI-SPEC error / empty / loading state copy (Plan 15-04)
// - E.164 + US-format phone validation (PART-05)
// - Add-to-Calendar secondary button + downloadIcs wiring (PART-13 surface A)
// - Status chip "Full" carries an icon (no color-only signal)
// - Orientation warning modal still triggers when period selected without orientation (PART-04 + PART-06)

import React from "react";
import { render, screen, waitFor, fireEvent, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — declared before component imports so vi.mock hoisting works
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getEvent: vi.fn(),
      createSignup: vi.fn(),
      // Legacy — kept for any test that still exercises the old flow.
      orientationStatus: vi.fn(),
      // Phase 21 — cross-week/cross-module credit check.
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

// Stub downloadIcs so the parallel Plan 15-02 lib does not need to exist
// at test time. The real implementation is exercised in calendar.test.js.
vi.mock("../../lib/calendar", () => ({
  downloadIcs: vi.fn(),
}));

import api from "../../lib/api";
import { toast } from "../../state/toast";
import { downloadIcs } from "../../lib/calendar";
import EventDetailPage, { isValidPhone } from "../public/EventDetailPage";

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const ORIENTATION_SLOT = {
  id: "slot-orient-1",
  slot_type: "orientation",
  date: "2026-04-22",
  start_time: "2026-04-22T09:00:00",
  end_time: "2026-04-22T11:00:00",
  location: "Room 101",
  capacity: 20,
  filled: 5,
};

const PERIOD_SLOT = {
  id: "slot-period-1",
  slot_type: "period",
  date: "2026-04-23",
  start_time: "2026-04-23T13:00:00",
  end_time: "2026-04-23T15:00:00",
  location: "Room 202",
  capacity: 20,
  filled: 7,
};

const FULL_SLOT = {
  id: "slot-full-1",
  slot_type: "period",
  date: "2026-04-24",
  start_time: "2026-04-24T10:00:00",
  end_time: "2026-04-24T12:00:00",
  location: "Room 303",
  capacity: 10,
  filled: 10, // full
};

const MOCK_EVENT = {
  id: "evt-1",
  slug: "crispr-carpinteria",
  title: "CRISPR at Carpinteria HS",
  quarter: "spring",
  year: 2026,
  week_number: 5,
  school: "Carpinteria HS",
  module_slug: "crispr",
  start_date: "2026-04-22",
  end_date: "2026-04-28",
  slots: [ORIENTATION_SLOT, PERIOD_SLOT, FULL_SLOT],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderDetailPage(eventId = "evt-1") {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/events/${eventId}`]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
          <Route path="/events" element={<div>Events list page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function fillIdentityForm() {
  await userEvent.type(screen.getByLabelText(/^first name$/i), "Alice");
  await userEvent.type(screen.getByLabelText(/^last name$/i), "Smith");
  await userEvent.type(screen.getByLabelText(/^email$/i), "alice@example.com");
  await userEvent.type(screen.getByLabelText(/^phone$/i), "(213) 867-5309");
}

async function clickFirstSignUpButton() {
  const buttons = await screen.findAllByRole("button", { name: /^sign up$/i });
  fireEvent.click(buttons[0]);
}

// The identity form submit button is the only <button type="submit"> on the page.
// Use this to disambiguate from the slot-row "Sign Up" buttons which share copy.
function clickFormSubmitButton(container) {
  const submit = container.querySelector('form button[type="submit"]');
  if (!submit) throw new Error("Form submit button not found");
  fireEvent.click(submit);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EventDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getEvent.mockResolvedValue(MOCK_EVENT);
  });

  // -------------------------------------------------------------------------
  // Loading / error / empty states (UI-SPEC §Plan 15-04)
  // -------------------------------------------------------------------------

  it("renders aria-busy loading region while fetching", async () => {
    let resolveGet;
    api.public.getEvent.mockImplementation(
      () => new Promise((r) => { resolveGet = r; })
    );
    const { container } = renderDetailPage();

    const busy = container.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();
    expect(busy.getAttribute("aria-live")).toBe("polite");

    await act(async () => { resolveGet(MOCK_EVENT); });
  });

  it("renders ErrorState with UI-SPEC copy + 'Try again' on fetch error", async () => {
    api.public.getEvent.mockRejectedValue(new Error("network down"));

    renderDetailPage();

    await waitFor(() => {
      expect(
        screen.getByText("We couldn't load this page")
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(/scitrek@ucsb\.edu/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i })
    ).toBeInTheDocument();
    // Old copy must be gone
    expect(screen.queryByText(/Could not load event/i)).not.toBeInTheDocument();
  });

  it("renders 'Every slot is full' empty state with Back to events action when no slots", async () => {
    api.public.getEvent.mockResolvedValue({ ...MOCK_EVENT, slots: [] });

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/every slot is full/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/this event is fully booked/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /back to events/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Slot grouping preserved (PART-04)
  // -------------------------------------------------------------------------

  it("renders both orientation and period slots with capacity+filled counts (PART-04)", async () => {
    renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    // Orientation row label is rendered (intro paragraph + slot row both mention orientation)
    const orientationLabels = await screen.findAllByText(/orientation/i);
    expect(orientationLabels.length).toBeGreaterThanOrEqual(1);

    // Period row labels are rendered (period slot rows). There are two period
    // slots (PERIOD_SLOT + FULL_SLOT), so "Period 1" appears once per period
    // group. Use getAllByText since both period dates produce a "Period 1".
    const periodLabels = screen.getAllByText(/^Period\s*1$/);
    expect(periodLabels.length).toBeGreaterThanOrEqual(1);

    // Filled counts now show capacity denominator per UI-SPEC (PART-04 / GAP-A):
    // "N of M filled" so the remaining headroom is visible even when a slot is not yet full.
    expect(screen.getByText(/5 of 20 filled/i)).toBeInTheDocument();
    expect(screen.getByText(/7 of 20 filled/i)).toBeInTheDocument();
  });

  it("Full slot renders a chip with both 'Full' text AND an XCircle icon (no color-only signal)", async () => {
    renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    // The aria-label "Slot full" identifies the chip wrapper unambiguously
    const fullChip = await screen.findByLabelText("Slot full");
    expect(fullChip).toBeInTheDocument();
    expect(fullChip.textContent).toMatch(/full/i);
    // Icon (svg from lucide-react) lives inside the chip
    expect(fullChip.querySelector("svg")).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // Sign-up flow (current button-based UI)
  // -------------------------------------------------------------------------

  it("reveals identity form when a Sign Up button is clicked", async () => {
    renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    expect(screen.queryByLabelText(/^first name$/i)).not.toBeInTheDocument();

    await clickFirstSignUpButton();

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/^last name$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^phone$/i)).toBeInTheDocument();
  });

  it("shows UI-SPEC validation copy when submitting empty form", async () => {
    const { container } = renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    await clickFirstSignUpButton();
    await screen.findByLabelText(/^first name$/i);

    clickFormSubmitButton(container);

    // Both first_name and last_name produce "Enter your full name" per UI-SPEC,
    // so getAllByText is the right query (two matches expected).
    await waitFor(() => {
      expect(screen.getAllByText(/enter your full name/i).length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByText(/enter your email address/i)).toBeInTheDocument();
    expect(screen.getByText(/enter your phone number/i)).toBeInTheDocument();

    // Old copy is gone
    expect(screen.queryByText(/first name is required/i)).not.toBeInTheDocument();
  });

  it("rejects invalid phone with UI-SPEC E.164/US copy", async () => {
    const { container } = renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");
    await clickFirstSignUpButton();
    await screen.findByLabelText(/^first name$/i);

    await userEvent.type(screen.getByLabelText(/^first name$/i), "Alice");
    await userEvent.type(screen.getByLabelText(/^last name$/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^email$/i), "alice@example.com");
    // Too short to match either US or E.164
    await userEvent.type(screen.getByLabelText(/^phone$/i), "12345");

    clickFormSubmitButton(container);

    await waitFor(() => {
      expect(
        screen.getByText(/use a us format: \(805\) 555-1234 or \+18055551234/i)
      ).toBeInTheDocument();
    });
  });

  it("submits successfully when orientation slot selected (no orientation warning needed)", async () => {
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "vol-1",
      signup_ids: ["sig-1"],
      magic_link_sent: true,
    });

    const { container } = renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    // The first Sign Up button corresponds to the orientation slot (orientations render first)
    await clickFirstSignUpButton();
    await screen.findByLabelText(/^first name$/i);

    await fillIdentityForm();
    clickFormSubmitButton(container);

    await waitFor(() => {
      expect(api.public.createSignup).toHaveBeenCalled();
    });
    // Orientation warning modal should not appear because an orientation slot is selected
    expect(
      screen.queryByText(/have you completed orientation/i)
    ).not.toBeInTheDocument();
  });

  it("calls orientationCheck with the event id when only a period slot is selected (Phase 21)", async () => {
    api.public.orientationCheck.mockResolvedValue({
      has_credit: true,
      has_attended_orientation: true,
      source: "attendance",
    });
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "vol-1",
      signup_ids: ["sig-1"],
      magic_link_sent: true,
    });

    const { container } = renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    // Sign Up buttons render in slot order: [orientation, period] (FULL_SLOT is a span chip, not a button)
    const signUpButtons = await screen.findAllByRole("button", { name: /^sign up$/i });
    // Click the second Sign Up button → period slot
    fireEvent.click(signUpButtons[1]);

    await screen.findByLabelText(/^first name$/i);
    await fillIdentityForm();
    clickFormSubmitButton(container);

    await waitFor(() => {
      expect(api.public.orientationCheck).toHaveBeenCalledWith(
        "alice@example.com",
        expect.any(String),
      );
    });
  });

  it("shows rate-limit toast on 429 error", async () => {
    const rateErr = new Error("rate limited");
    rateErr.status = 429;
    api.public.createSignup.mockRejectedValue(rateErr);

    const { container } = renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    await clickFirstSignUpButton();
    await screen.findByLabelText(/^first name$/i);

    await fillIdentityForm();
    clickFormSubmitButton(container);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/too many submissions|please wait/i)
      );
    });
  });

  // -------------------------------------------------------------------------
  // Add to calendar (PART-13 surface A, Task 2)
  // -------------------------------------------------------------------------

  it("renders 'Add to calendar' secondary button below event metadata", async () => {
    renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    expect(
      screen.getByRole("button", { name: /add to calendar/i })
    ).toBeInTheDocument();
  });

  it("clicking 'Add to calendar' calls downloadIcs with UI-SPEC filename and shows success toast", async () => {
    renderDetailPage();
    await screen.findByText("CRISPR at Carpinteria HS");

    fireEvent.click(screen.getByRole("button", { name: /add to calendar/i }));

    expect(downloadIcs).toHaveBeenCalledTimes(1);
    const callArg = downloadIcs.mock.calls[0][0];
    expect(callArg).toHaveProperty("event");
    expect(callArg).toHaveProperty("slot");
    expect(callArg).toHaveProperty("filename");
    expect(callArg.filename).toMatch(/^scitrek-crispr-carpinteria-2026-04-22\.ics$/);
    // Selection precedence: no selection yet → falls back to first non-full orientation slot
    expect(callArg.slot.id).toBe("slot-orient-1");

    expect(toast.success).toHaveBeenCalledWith(
      "Calendar file saved. Open it to add to your calendar."
    );
  });

  it("does NOT render 'Add to calendar' when there are no slots", async () => {
    api.public.getEvent.mockResolvedValue({ ...MOCK_EVENT, slots: [] });

    renderDetailPage();
    await screen.findByText(/every slot is full/i);

    expect(
      screen.queryByRole("button", { name: /add to calendar/i })
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// isValidPhone unit coverage (PART-05)
// ---------------------------------------------------------------------------

describe("isValidPhone (PART-05)", () => {
  it("accepts US 10-digit formats", () => {
    expect(isValidPhone("8055551234")).toBe(true);
    expect(isValidPhone("(805) 555-1234")).toBe(true);
    expect(isValidPhone("805-555-1234")).toBe(true);
    expect(isValidPhone("805.555.1234")).toBe(true);
    expect(isValidPhone("805 555 1234")).toBe(true);
  });

  it("accepts US 11-digit with leading 1", () => {
    expect(isValidPhone("18055551234")).toBe(true);
    expect(isValidPhone("1 (805) 555-1234")).toBe(true);
  });

  it("accepts E.164 format", () => {
    expect(isValidPhone("+18055551234")).toBe(true);
    expect(isValidPhone("+447911123456")).toBe(true); // UK
    expect(isValidPhone("+819012345678")).toBe(true); // Japan
  });

  it("rejects invalid input", () => {
    expect(isValidPhone("")).toBe(false);
    expect(isValidPhone(null)).toBe(false);
    expect(isValidPhone(undefined)).toBe(false);
    expect(isValidPhone("12345")).toBe(false); // too short
    expect(isValidPhone("+0123456789")).toBe(false); // E.164 country must start 1-9
    expect(isValidPhone("abcdefghij")).toBe(false);
    expect(isValidPhone("+1234567")).toBe(false); // E.164 too short (under 8 digits)
  });
});
