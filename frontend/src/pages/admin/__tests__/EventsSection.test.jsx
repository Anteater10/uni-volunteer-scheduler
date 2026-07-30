// src/pages/admin/__tests__/EventsSection.test.jsx
//
// Covers the admin EventForm slot management added in v1.2-final:
// - Pure helpers: diffSlots, slotFormToApiPayload, validateSlot, loadedSlotToForm
// - Form behaviour: rendering, add/remove slots, validation errors, create payload shape
// - Edit-mode diff: POST for new rows, PATCH for changed rows, DELETE for removed rows

import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/api", () => {
  const events = {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  };
  const slots = {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  };
  const admin = {
    modules: {
      list: vi.fn(),
      create: vi.fn(),
    },
  };
  const apiObj = {
    events,
    slots,
    admin,
    // fix/ux-quarter-batch: the QuarterSelectionProvider (ended-quarter
    // tests) loads the quarter list through this.
    public: { getQuarters: vi.fn().mockResolvedValue([]) },
  };
  return { api: apiObj, default: apiObj };
});

vi.mock("../../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: vi.fn(),
}));

import { api } from "../../../lib/api";
import EventsSection, {
  diffSlots,
  slotFormToApiPayload,
  validateSlot,
  loadedSlotToForm,
} from "../EventsSection";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithQuery(ui) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const FIXTURE_MODULES = [
  { slug: "crispr-intro", name: "CRISPR Intro", family_key: "crispr-intro" },
  { slug: "glucose", name: "Glucose Sensing", family_key: "glucose" },
];

const FIXTURE_EVENT = {
  id: "evt-1",
  title: "Existing Event",
  description: "desc",
  location: "Hall A",
  visibility: "public",
  start_date: "2026-04-20T09:00:00Z",
  end_date: "2026-04-20T17:00:00Z",
  max_signups_per_user: null,
  school: "SciTrek HS",
  module_slug: "crispr-intro",
  slots: [
    {
      id: "slot-1",
      start_time: "2026-04-20T09:00:00Z",
      end_time: "2026-04-20T10:00:00Z",
      capacity: 20,
      current_count: 0,
      slot_type: "orientation",
      date: "2026-04-20",
      location: "Hall A",
    },
    {
      id: "slot-2",
      start_time: "2026-04-20T10:30:00Z",
      end_time: "2026-04-20T12:00:00Z",
      capacity: 30,
      current_count: 5,
      slot_type: "period",
      date: "2026-04-20",
      location: "Hall B",
    },
  ],
};

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

describe("loadedSlotToForm", () => {
  it("maps ISO slot into form-shape with HH:MM wall-clock", () => {
    const form = loadedSlotToForm(FIXTURE_EVENT.slots[0]);
    expect(form.id).toBe("slot-1");
    expect(form.slot_type).toBe("orientation");
    expect(form.date).toBe("2026-04-20");
    expect(form.capacity).toBe("20");
    expect(form.location).toBe("Hall A");
    expect(form.current_count).toBe(0);
    // HH:MM strings — any reasonable format is fine, just assert shape
    expect(form.start_time).toMatch(/^\d{2}:\d{2}$/);
    expect(form.end_time).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe("slotFormToApiPayload", () => {
  it("combines date + time into ISO strings and coerces capacity to number", () => {
    const payload = slotFormToApiPayload({
      slot_type: "period",
      date: "2026-04-20",
      start_time: "09:00",
      end_time: "10:30",
      capacity: "25",
      location: "Room 1",
    });
    expect(payload.slot_type).toBe("period");
    expect(payload.date).toBe("2026-04-20");
    expect(payload.capacity).toBe(25);
    expect(payload.location).toBe("Room 1");
    expect(typeof payload.start_time).toBe("string");
    expect(payload.start_time).toMatch(/^2026-04-20T/);
    expect(typeof payload.end_time).toBe("string");
    expect(payload.end_time).toMatch(/^2026-04-20T/);
  });

  it("treats empty location as null", () => {
    const payload = slotFormToApiPayload({
      slot_type: "period",
      date: "2026-04-20",
      start_time: "09:00",
      end_time: "10:00",
      capacity: "5",
      location: "   ",
    });
    expect(payload.location).toBeNull();
  });
});

describe("validateSlot", () => {
  const evStart = "2026-04-20T09:00:00Z";
  const evEnd = "2026-04-20T17:00:00Z";

  it("returns null when all fields valid", () => {
    expect(
      validateSlot(
        {
          slot_type: "period",
          date: "2026-04-20",
          start_time: "10:00",
          end_time: "11:00",
          capacity: "10",
          location: "",
        },
        evStart,
        evEnd,
      ),
    ).toBeNull();
  });

  it("rejects end ≤ start", () => {
    const err = validateSlot(
      {
        slot_type: "period",
        date: "2026-04-20",
        start_time: "12:00",
        end_time: "11:00",
        capacity: "10",
      },
      evStart,
      evEnd,
    );
    expect(err).toMatch(/End time must be after start/i);
  });

  it("rejects non-positive capacity", () => {
    const err = validateSlot(
      {
        slot_type: "period",
        date: "2026-04-20",
        start_time: "10:00",
        end_time: "11:00",
        capacity: "0",
      },
      evStart,
      evEnd,
    );
    expect(err).toMatch(/capacity/i);
  });

  it("rejects missing date or times", () => {
    expect(
      validateSlot(
        { slot_type: "period", date: "", start_time: "10:00", end_time: "11:00", capacity: "5" },
        evStart,
        evEnd,
      ),
    ).toBeTruthy();
  });
});

describe("diffSlots", () => {
  function makeSlot(id, overrides = {}) {
    return {
      id,
      slot_type: "period",
      date: "2026-04-20",
      start_time: "10:00",
      end_time: "11:00",
      capacity: "10",
      location: "",
      current_count: 0,
      ...overrides,
    };
  }

  it("detects new (no id), changed, and removed rows", () => {
    const initial = [makeSlot("a"), makeSlot("b", { capacity: "20" })];
    const draft = [
      makeSlot("a"), // unchanged
      makeSlot("b", { capacity: "99" }), // changed capacity
      makeSlot(undefined, { start_time: "12:00", end_time: "13:00" }), // new
    ];
    const { creates, updates, deletes } = diffSlots(initial, draft);
    expect(creates).toHaveLength(1);
    expect(updates).toHaveLength(1);
    expect(updates[0].id).toBe("b");
    expect(deletes).toEqual(expect.arrayContaining([]));
  });

  it("flags removed rows as deletes", () => {
    const initial = [makeSlot("a"), makeSlot("b")];
    const draft = [makeSlot("a")];
    const { deletes } = diffSlots(initial, draft);
    expect(deletes).toEqual(["b"]);
  });

  it("returns empty ops when no changes", () => {
    const initial = [makeSlot("a")];
    const draft = [makeSlot("a")];
    const { creates, updates, deletes } = diffSlots(initial, draft);
    expect(creates).toHaveLength(0);
    expect(updates).toHaveLength(0);
    expect(deletes).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Component tests
// ---------------------------------------------------------------------------

describe("EventsSection — create flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.events.list.mockResolvedValue([]);
    api.events.create.mockResolvedValue({ id: "new-evt" });
    api.admin.modules.list.mockResolvedValue(FIXTURE_MODULES);
    api.admin.modules.create.mockResolvedValue({
      slug: "new-module",
      name: "New Module",
      family_key: "new-module",
    });
  });

  it("renders the create form with a blank slot row and school field", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
    expect(
      await screen.findByRole("heading", { name: /New event/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/School/i)).toBeInTheDocument();
    expect(screen.getByTestId("slot-row-0")).toBeInTheDocument();
  });

  it("add and remove slot buttons update the list", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^Add slot$/i }));
    expect(screen.getByTestId("slot-row-1")).toBeInTheDocument();

    const row1 = screen.getByTestId("slot-row-1");
    fireEvent.click(within(row1).getByRole("button", { name: /Remove/i }));
    expect(screen.queryByTestId("slot-row-1")).not.toBeInTheDocument();
  });

  // Native time inputs ignore the wheel entirely, but admins set dozens of
  // slot times per sitting — so the field steps on scroll once focused.
  it("steps a slot time with the mouse wheel while focused", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));

    const start = await screen.findByLabelText(/Slot 1 start time/i);
    fireEvent.change(start, { target: { value: "09:00" } });
    start.focus();

    fireEvent.wheel(start, { deltaY: -1 }); // up = later
    expect(start.value).toBe("09:05");

    fireEvent.wheel(start, { deltaY: 1 }); // down = earlier
    expect(start.value).toBe("09:00");

    fireEvent.wheel(start, { deltaY: -1, shiftKey: true }); // shift = by the hour
    expect(start.value).toBe("10:00");
  });

  // Safari renders <input type="time"> with no picker at all, so the dropdown
  // is ours rather than the browser's.
  it("opens a time dropdown on click and picks a value", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));

    const start = await screen.findByLabelText(/Slot 1 start time/i);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    fireEvent.click(start);
    expect(await screen.findByRole("listbox")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("option", { name: "9:30 AM" }));
    expect(start.value).toBe("09:30");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  // Scrolling the long modal must never silently rewrite a time the cursor
  // happens to pass over — the field has to be focused first.
  it("ignores the wheel when the time field is not focused", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));

    const start = await screen.findByLabelText(/Slot 1 start time/i);
    fireEvent.change(start, { target: { value: "09:00" } });
    start.blur();

    fireEvent.wheel(start, { deltaY: -1 });
    expect(start.value).toBe("09:00");
  });

  it("blocks submit when a slot has invalid times", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));

    fireEvent.change(screen.getByLabelText(/Title \*/i), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText(/^Start \*/i), {
      target: { value: "2026-04-20T09:00" },
    });
    fireEvent.change(screen.getByLabelText(/^End \*/i), {
      target: { value: "2026-04-20T17:00" },
    });
    // Pick a module so we clear the module-required check and actually reach slot validation.
    await screen.findByRole("option", { name: /CRISPR Intro/i });
    fireEvent.change(screen.getByLabelText(/Module \*/i), {
      target: { value: "crispr-intro" },
    });

    const row = screen.getByTestId("slot-row-0");
    fireEvent.change(within(row).getByLabelText(/Slot 1 date/i), {
      target: { value: "2026-04-20" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 start time/i), {
      target: { value: "12:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 end time/i), {
      target: { value: "11:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 capacity/i), {
      target: { value: "10" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));
    expect(
      await screen.findByTestId("slot-error-0"),
    ).toHaveTextContent(/End time must be after start/i);
    expect(api.events.create).not.toHaveBeenCalled();
  });

  it("submits a create payload with slots array", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));

    fireEvent.change(screen.getByLabelText(/Title \*/i), {
      target: { value: "Science Fair" },
    });
    fireEvent.change(screen.getByLabelText(/^Start \*/i), {
      target: { value: "2026-04-20T09:00" },
    });
    fireEvent.change(screen.getByLabelText(/^End \*/i), {
      target: { value: "2026-04-20T17:00" },
    });

    // Pick a module (required) — wait for options to load.
    await screen.findByRole("option", { name: /CRISPR Intro/i });
    fireEvent.change(screen.getByLabelText(/Module \*/i), {
      target: { value: "crispr-intro" },
    });

    const row = screen.getByTestId("slot-row-0");
    fireEvent.change(within(row).getByLabelText(/Slot 1 date/i), {
      target: { value: "2026-04-20" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 start time/i), {
      target: { value: "10:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 end time/i), {
      target: { value: "11:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 capacity/i), {
      target: { value: "12" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => expect(api.events.create).toHaveBeenCalledTimes(1));
    const payload = api.events.create.mock.calls[0][0];
    expect(payload.title).toBe("Science Fair");
    expect(payload.module_slug).toBe("crispr-intro");
    expect(Array.isArray(payload.slots)).toBe(true);
    expect(payload.slots).toHaveLength(1);
    expect(payload.slots[0].capacity).toBe(12);
    expect(payload.slots[0].slot_type).toBe("period");
  });

  it("blocks submit when no module is picked", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));

    fireEvent.change(screen.getByLabelText(/Title \*/i), {
      target: { value: "No Module Event" },
    });
    fireEvent.change(screen.getByLabelText(/^Start \*/i), {
      target: { value: "2026-04-20T09:00" },
    });
    fireEvent.change(screen.getByLabelText(/^End \*/i), {
      target: { value: "2026-04-20T17:00" },
    });
    const row = screen.getByTestId("slot-row-0");
    fireEvent.change(within(row).getByLabelText(/Slot 1 date/i), {
      target: { value: "2026-04-20" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 start time/i), {
      target: { value: "10:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 end time/i), {
      target: { value: "11:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 capacity/i), {
      target: { value: "12" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/pick a module/i);
    expect(api.events.create).not.toHaveBeenCalled();
  });
});

describe("EventsSection — edit flow diff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.events.list.mockResolvedValue([FIXTURE_EVENT]);
    api.events.update.mockResolvedValue({});
    api.slots.create.mockResolvedValue({});
    api.slots.update.mockResolvedValue({});
    api.slots.delete.mockResolvedValue({});
    api.admin.modules.list.mockResolvedValue(FIXTURE_MODULES);
  });

  it("renders existing slots with their values and signup count", async () => {
    renderWithQuery(<EventsSection />);
    // FIXTURE_EVENT is dated in the past, but the default scope is now
    // "All" so the row (and its Edit button) is visible immediately.
    fireEvent.click(await screen.findByRole("button", { name: /^Edit$/i }));

    expect(await screen.findByTestId("slot-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("slot-row-1")).toBeInTheDocument();
    // slot-2 has 5 signups, Remove is disabled
    const row1 = screen.getByTestId("slot-row-1");
    const removeBtn = within(row1).getByRole("button", { name: /Remove/i });
    expect(removeBtn).toBeDisabled();
  });

  it("issues PATCH for changed capacity, POST for new slot, DELETE for removed", async () => {
    // Override: drop slot-2's signups so it can be removed in this test.
    const editable = {
      ...FIXTURE_EVENT,
      slots: [
        { ...FIXTURE_EVENT.slots[0] },
        { ...FIXTURE_EVENT.slots[1], current_count: 0 },
      ],
    };
    api.events.list.mockResolvedValue([editable]);

    renderWithQuery(<EventsSection />);
    // Past-dated fixture is visible under the default "All" scope.
    fireEvent.click(await screen.findByRole("button", { name: /^Edit$/i }));
    await screen.findByTestId("slot-row-0");

    // change capacity on row 0 (existing slot-1) → PATCH
    fireEvent.change(
      within(screen.getByTestId("slot-row-0")).getByLabelText(/Slot 1 capacity/i),
      { target: { value: "40" } },
    );

    // remove row 1 (existing slot-2) → DELETE
    fireEvent.click(
      within(screen.getByTestId("slot-row-1")).getByRole("button", { name: /Remove/i }),
    );

    // add a new slot → POST
    fireEvent.click(screen.getByRole("button", { name: /^Add slot$/i }));
    const newRow = screen.getByTestId("slot-row-1");
    fireEvent.change(within(newRow).getByLabelText(/Slot 2 date/i), {
      target: { value: "2026-04-20" },
    });
    fireEvent.change(within(newRow).getByLabelText(/Slot 2 start time/i), {
      target: { value: "13:00" },
    });
    fireEvent.change(within(newRow).getByLabelText(/Slot 2 end time/i), {
      target: { value: "14:00" },
    });
    fireEvent.change(within(newRow).getByLabelText(/Slot 2 capacity/i), {
      target: { value: "15" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => expect(api.events.update).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.slots.update).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.slots.create).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.slots.delete).toHaveBeenCalledTimes(1));

    expect(api.slots.update.mock.calls[0][0]).toBe("slot-1");
    expect(api.slots.update.mock.calls[0][1].capacity).toBe(40);
    expect(api.slots.delete).toHaveBeenCalledWith("slot-2");
    expect(api.slots.create.mock.calls[0][0]).toBe("evt-1");
    expect(api.slots.create.mock.calls[0][1].capacity).toBe(15);
  });
});


// ---------------------------------------------------------------------------
// fix/ux-quarter-batch — the list defaults to ALL events (upcoming + past),
// completed events are badged and file under Past, and an ended quarter
// flips into history mode: no event creation, status filter instead of the
// meaningless Upcoming/Past pair.
// ---------------------------------------------------------------------------

import { QuarterSelectionProvider } from "../../../state/QuarterSelectionContext";

const future = new Date(Date.now() + 7 * 86400e3).toISOString();
const futureEnd = new Date(Date.now() + 8 * 86400e3).toISOString();
const past = new Date(Date.now() - 8 * 86400e3).toISOString();
const pastEnd = new Date(Date.now() - 7 * 86400e3).toISOString();

const SCOPE_LIST = [
  {
    id: "e-completed",
    title: "Completed early",
    // Dates still ahead, but every slot was ended — completed wins.
    start_date: future,
    end_date: futureEnd,
    completed_at: new Date().toISOString(),
    location: "Lab 1",
  },
  {
    id: "e-ended",
    title: "Dates went by",
    start_date: past,
    end_date: pastEnd,
    completed_at: null,
    location: "Lab 2",
  },
  {
    id: "e-upcoming",
    title: "Still to come",
    start_date: future,
    end_date: futureEnd,
    completed_at: null,
    location: "Lab 3",
  },
];

describe("EventsSection — completion badges and default-All scope", () => {
  beforeEach(() => {
    window.localStorage.clear();
    api.events.list.mockResolvedValue(SCOPE_LIST);
    api.admin.modules.list.mockResolvedValue([]);
  });

  it("shows every event by default — upcoming and past together, badged", async () => {
    renderWithQuery(<EventsSection />);
    // All three rows visible without touching any filter.
    expect(await screen.findByText("Completed early")).toBeInTheDocument();
    expect(screen.getByText("Dates went by")).toBeInTheDocument();
    expect(screen.getByText("Still to come")).toBeInTheDocument();
    expect(screen.getByLabelText("Time filter")).toHaveValue("all");
    // And each carries its status badge.
    expect(screen.getByText(/✓ Completed/)).toBeInTheDocument();
    expect(screen.getByText(/Ended — not closed out/)).toBeInTheDocument();
    expect(
      within(screen.getByRole("table")).getByText("Upcoming"),
    ).toBeInTheDocument();
  });

  it("files a completed event under Past even when its dates are ahead", async () => {
    renderWithQuery(<EventsSection />);
    await screen.findByText("Still to come");

    fireEvent.change(screen.getByLabelText("Time filter"), {
      target: { value: "past" },
    });
    expect(await screen.findByText("Completed early")).toBeInTheDocument();
    expect(screen.getByText("Dates went by")).toBeInTheDocument();
    expect(screen.queryByText("Still to come")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Time filter"), {
      target: { value: "upcoming" },
    });
    expect(await screen.findByText("Still to come")).toBeInTheDocument();
    expect(screen.queryByText("Completed early")).not.toBeInTheDocument();
  });
});

describe("EventsSection — ended quarter history mode", () => {
  const OLD_Q = {
    id: "q-old",
    display_name: "Spring 2026",
    season: "spring",
    year: 2026,
    start_date: "2026-03-30",
    end_date: "2026-06-13",
    archived_at: null,
  };

  function renderInEndedQuarter() {
    window.localStorage.setItem("admin.selectedQuarterId", "q-old");
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <QuarterSelectionProvider>
            <EventsSection />
          </QuarterSelectionProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  beforeEach(() => {
    window.localStorage.clear();
    api.public.getQuarters.mockResolvedValue([OLD_Q]);
    api.events.list.mockResolvedValue([
      {
        id: "e-old-done",
        title: "Old and completed",
        start_date: "2026-04-07T15:00:00Z",
        end_date: "2026-04-09T19:00:00Z",
        completed_at: "2026-04-09T19:12:00Z",
        location: "Lab 1",
      },
      {
        id: "e-old-open",
        title: "Old but never closed out",
        start_date: "2026-06-02T15:00:00Z",
        end_date: "2026-06-02T19:00:00Z",
        completed_at: null,
        location: "Lab 2",
      },
    ]);
    api.admin.modules.list.mockResolvedValue([]);
  });

  it("hides event creation and explains the quarter is history", async () => {
    renderInEndedQuarter();
    expect(await screen.findByTestId("ended-quarter-strip")).toHaveTextContent(
      /Spring 2026 ended/,
    );
    expect(screen.queryByText("+ New event")).not.toBeInTheDocument();
    // Escape hatch back to the live schedule.
    expect(
      screen.getByRole("button", { name: /back to current quarter/i }),
    ).toBeInTheDocument();
  });

  it("swaps Upcoming/Past for a completion-status filter", async () => {
    renderInEndedQuarter();
    await screen.findByText("Old and completed");

    const filter = screen.getByLabelText("Time filter");
    // No time-based options — everything here is in the past.
    expect(within(filter).queryByText("Upcoming")).not.toBeInTheDocument();

    fireEvent.change(filter, { target: { value: "open" } });
    expect(await screen.findByText("Old but never closed out")).toBeInTheDocument();
    expect(screen.queryByText("Old and completed")).not.toBeInTheDocument();

    fireEvent.change(filter, { target: { value: "completed" } });
    expect(await screen.findByText("Old and completed")).toBeInTheDocument();
    expect(screen.queryByText("Old but never closed out")).not.toBeInTheDocument();
  });

  // Sweep remediation task 5: ended quarters are read-only history — the
  // server now rejects update/delete against them (422 QUARTER_READONLY),
  // so the row actions that would trigger those must not even render.
  // Duplicate is exempt: it always creates the copy in a *target* quarter
  // (never the source's), so it stays available from history too.
  it("hides Edit and Delete row actions but keeps Duplicate available", async () => {
    renderInEndedQuarter();
    // Await both rows: the quarter list itself loads async (Quarter select
    // provider), so the events query briefly refetches under a new query
    // key once the selected quarter resolves — settle past that first.
    await screen.findByText("Old and completed");
    await screen.findByText("Old but never closed out");

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows.length).toBeGreaterThan(0);
    rows.forEach((row) => {
      expect(
        within(row).queryByRole("button", { name: /^Edit$/i }),
      ).not.toBeInTheDocument();
      expect(
        within(row).queryByRole("button", { name: /^Delete$/i }),
      ).not.toBeInTheDocument();
      expect(
        within(row).getByRole("button", { name: /^Duplicate$/i }),
      ).toBeInTheDocument();
    });
  });
});
