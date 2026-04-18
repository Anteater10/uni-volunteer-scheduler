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
    clone: vi.fn(),
  };
  const slots = {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  };
  const apiObj = { events, slots };
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
    fireEvent.click(await screen.findByRole("button", { name: /\+ Add slot/i }));
    expect(screen.getByTestId("slot-row-1")).toBeInTheDocument();

    const row1 = screen.getByTestId("slot-row-1");
    fireEvent.click(within(row1).getByRole("button", { name: /Remove/i }));
    expect(screen.queryByTestId("slot-row-1")).not.toBeInTheDocument();
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
    expect(Array.isArray(payload.slots)).toBe(true);
    expect(payload.slots).toHaveLength(1);
    expect(payload.slots[0].capacity).toBe(12);
    expect(payload.slots[0].slot_type).toBe("period");
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
  });

  it("renders existing slots with their values and signup count", async () => {
    renderWithQuery(<EventsSection />);
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
    fireEvent.click(screen.getByRole("button", { name: /\+ Add slot/i }));
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
