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
  const shifts = {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    reorder: vi.fn(),
    addSession: vi.fn(),
    updateSession: vi.fn(),
    deleteSession: vi.fn(),
    reorderSessions: vi.fn(),
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
    shifts,
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
  diffShifts,
  shiftFormToApiPayload,
  validateShift,
  loadedShiftToForm,
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
    // Sessions still appear in the flat `slots` list (that's what check-in and
    // ICS read), but they are edited through their shift, not as rows here.
    {
      id: "slot-2",
      start_time: "2026-04-20T10:30:00Z",
      end_time: "2026-04-20T12:00:00Z",
      capacity: 1,
      current_count: 0,
      slot_type: "period",
      shift_id: "shift-1",
      name: "Period 1",
      date: "2026-04-20",
      location: "Hall B",
    },
  ],
  shifts: [
    {
      id: "shift-1",
      event_id: "evt-1",
      name: "Tue 1:00pm",
      sort_order: 0,
      capacity: 30,
      current_count: 5,
      sessions: [
        {
          id: "slot-2",
          start_time: "2026-04-20T10:30:00Z",
          end_time: "2026-04-20T12:00:00Z",
          capacity: 1,
          current_count: 0,
          slot_type: "period",
          shift_id: "shift-1",
          name: "Period 1",
          sort_order: 0,
          date: "2026-04-20",
          location: "Hall B",
        },
      ],
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
// Shift helpers (2026-08-02 shifts design)
// ---------------------------------------------------------------------------

describe("loadedShiftToForm", () => {
  it("maps a ShiftRead into form-shape with its sessions in order", () => {
    const form = loadedShiftToForm(FIXTURE_EVENT.shifts[0]);
    expect(form.id).toBe("shift-1");
    expect(form.name).toBe("Tue 1:00pm");
    expect(form.capacity).toBe("30");
    expect(form.current_count).toBe(5);
    expect(form.sessions).toHaveLength(1);
    expect(form.sessions[0].id).toBe("slot-2");
    expect(form.sessions[0].name).toBe("Period 1");
    expect(form.sessions[0].date).toBe("2026-04-20");
    expect(form.sessions[0].start_time).toMatch(/^\d{2}:\d{2}$/);
  });

  it("orders sessions by sort_order, not by the order they arrived in", () => {
    const form = loadedShiftToForm({
      id: "s",
      name: "n",
      capacity: 3,
      current_count: 0,
      sessions: [
        {
          id: "b",
          sort_order: 1,
          start_time: "2026-04-21T10:00:00Z",
          end_time: "2026-04-21T11:00:00Z",
          date: "2026-04-21",
        },
        {
          id: "a",
          sort_order: 0,
          start_time: "2026-04-20T10:00:00Z",
          end_time: "2026-04-20T11:00:00Z",
          date: "2026-04-20",
        },
      ],
    });
    expect(form.sessions.map((s) => s.id)).toEqual(["a", "b"]);
  });
});

describe("shiftFormToApiPayload", () => {
  it("numbers capacity, stamps sort_order, and combines each session's date + time", () => {
    const payload = shiftFormToApiPayload(
      {
        name: "  Tue 1:00pm  ",
        capacity: "18",
        sessions: [
          {
            name: " Period 1 ",
            date: "2026-04-20",
            start_time: "10:00",
            end_time: "11:00",
            location: "   ",
          },
          {
            name: "",
            date: "2026-04-21",
            start_time: "10:00",
            end_time: "11:00",
            location: "Room 2",
          },
        ],
      },
      2,
    );
    expect(payload.name).toBe("Tue 1:00pm");
    expect(payload.capacity).toBe(18);
    expect(payload.sort_order).toBe(2);
    expect(payload.sessions).toHaveLength(2);
    expect(payload.sessions[0].name).toBe("Period 1");
    expect(payload.sessions[0].location).toBeNull();
    expect(payload.sessions[0].start_time).toMatch(/^2026-04-20T/);
    // sort_order comes from position, so a drag needs no extra field.
    expect(payload.sessions.map((s) => s.sort_order)).toEqual([0, 1]);
    expect(payload.sessions[1].name).toBeNull();
  });
});

describe("validateShift", () => {
  const evStart = "2026-04-20T09:00:00Z";
  const evEnd = "2026-04-22T17:00:00Z";
  const ok = {
    name: "Tue 1:00pm",
    capacity: "10",
    sessions: [
      { date: "2026-04-20", start_time: "10:00", end_time: "11:00" },
      { date: "2026-04-21", start_time: "10:00", end_time: "11:00" },
    ],
  };

  it("returns null for a well-formed multi-session shift", () => {
    expect(validateShift(ok, evStart, evEnd)).toBeNull();
  });

  it("requires a name — it is what volunteers pick from", () => {
    expect(validateShift({ ...ok, name: "  " }, evStart, evEnd)).toMatch(/name/i);
  });

  it("rejects non-positive capacity", () => {
    expect(validateShift({ ...ok, capacity: "0" }, evStart, evEnd)).toMatch(
      /capacity/i,
    );
  });

  it("names the offending session when one is malformed", () => {
    const err = validateShift(
      {
        ...ok,
        sessions: [
          ok.sessions[0],
          { date: "2026-04-21", start_time: "12:00", end_time: "11:00" },
        ],
      },
      evStart,
      evEnd,
    );
    expect(err).toMatch(/Session 2/);
    expect(err).toMatch(/end time must be after start/i);
  });

  it("rejects a session outside the event window", () => {
    const err = validateShift(
      { ...ok, sessions: [{ date: "2026-04-30", start_time: "10:00", end_time: "11:00" }] },
      evStart,
      evEnd,
    );
    expect(err).toMatch(/after the event end/i);
  });

  it("rejects a shift with no sessions at all", () => {
    expect(validateShift({ ...ok, sessions: [] }, evStart, evEnd)).toMatch(
      /at least one session/i,
    );
  });
});

describe("diffShifts", () => {
  function makeShift(id, overrides = {}) {
    return {
      id,
      name: "Tue 1:00pm",
      capacity: "10",
      current_count: 0,
      sessions: [
        {
          id: `${id}-s1`,
          name: "Period 1",
          date: "2026-04-20",
          start_time: "10:00",
          end_time: "11:00",
          location: "",
        },
      ],
      ...overrides,
    };
  }

  it("returns nothing when nothing moved", () => {
    const { creates, updates, deletes } = diffShifts([makeShift("a")], [makeShift("a")]);
    expect(creates).toHaveLength(0);
    expect(updates).toHaveLength(0);
    expect(deletes).toHaveLength(0);
  });

  it("flags an id-less shift as a create carrying its position", () => {
    const draft = [makeShift("a"), makeShift(undefined, { name: "Wed 10am" })];
    const { creates } = diffShifts([makeShift("a")], draft);
    expect(creates).toHaveLength(1);
    expect(creates[0].index).toBe(1);
    expect(creates[0].shift.name).toBe("Wed 10am");
  });

  it("flags a dropped shift as a delete", () => {
    const { deletes } = diffShifts([makeShift("a"), makeShift("b")], [makeShift("a")]);
    expect(deletes).toEqual(["b"]);
  });

  it("marks a capacity change as a field update", () => {
    const { updates } = diffShifts(
      [makeShift("a")],
      [makeShift("a", { capacity: "25" })],
    );
    expect(updates).toHaveLength(1);
    expect(updates[0].fieldsChanged).toBe(true);
    expect(updates[0].sessionUpdates).toHaveLength(0);
  });

  it("treats a reorder as a field update — position is the sort_order", () => {
    const initial = [makeShift("a"), makeShift("b")];
    const draft = [makeShift("b"), makeShift("a")];
    const { updates } = diffShifts(initial, draft);
    expect(updates.map((u) => u.shift.id).sort()).toEqual(["a", "b"]);
    expect(updates.every((u) => u.fieldsChanged)).toBe(true);
  });

  it("diffs sessions inside a surviving shift", () => {
    const initial = [makeShift("a")];
    const draft = [
      makeShift("a", {
        sessions: [
          {
            id: "a-s1",
            name: "Period 1",
            date: "2026-04-20",
            start_time: "13:00", // moved
            end_time: "14:00",
            location: "",
          },
          {
            // no id → a new session
            name: "Period 2",
            date: "2026-04-21",
            start_time: "10:00",
            end_time: "11:00",
            location: "",
          },
        ],
      }),
    ];
    const { updates } = diffShifts(initial, draft);
    expect(updates).toHaveLength(1);
    expect(updates[0].fieldsChanged).toBe(false);
    expect(updates[0].sessionUpdates).toHaveLength(1);
    expect(updates[0].sessionUpdates[0].session.id).toBe("a-s1");
    expect(updates[0].sessionCreates).toHaveLength(1);
    expect(updates[0].sessionCreates[0].index).toBe(1);
    expect(updates[0].sessionDeletes).toHaveLength(0);
  });

  it("flags a removed session as a session delete", () => {
    const initial = [
      makeShift("a", {
        sessions: [
          {
            id: "a-s1",
            name: "P1",
            date: "2026-04-20",
            start_time: "10:00",
            end_time: "11:00",
            location: "",
          },
          {
            id: "a-s2",
            name: "P2",
            date: "2026-04-21",
            start_time: "10:00",
            end_time: "11:00",
            location: "",
          },
        ],
      }),
    ];
    const draft = [makeShift("a", { sessions: [initial[0].sessions[0]] })];
    const { updates } = diffShifts(initial, draft);
    expect(updates[0].sessionDeletes).toEqual(["a-s2"]);
  });

  it("a pure session drag becomes session updates, not a shift update", () => {
    const sessions = [
      {
        id: "a-s1",
        name: "P1",
        date: "2026-04-20",
        start_time: "10:00",
        end_time: "11:00",
        location: "",
      },
      {
        id: "a-s2",
        name: "P2",
        date: "2026-04-21",
        start_time: "10:00",
        end_time: "11:00",
        location: "",
      },
    ];
    const initial = [makeShift("a", { sessions })];
    const draft = [makeShift("a", { sessions: [sessions[1], sessions[0]] })];
    const { updates } = diffShifts(initial, draft);
    expect(updates[0].fieldsChanged).toBe(false);
    expect(updates[0].sessionUpdates.map((u) => [u.session.id, u.index])).toEqual([
      ["a-s2", 0],
      ["a-s1", 1],
    ]);
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

  // A new event starts as one blank shift and no orientation slots: the shift
  // is what volunteers book, orientation is an occasional extra.
  it("renders the create form with a blank shift row and school field", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
    expect(
      await screen.findByRole("heading", { name: /New event/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/School/i)).toBeInTheDocument();
    expect(screen.getByTestId("shift-row-0")).toBeInTheDocument();
    expect(screen.queryByTestId("slot-row-0")).not.toBeInTheDocument();
  });

  // Laying out an event's shifts takes minutes of typing, and the modal holds
  // all of it in local state — so a stray click on the backdrop used to wipe
  // the lot with no warning. Once anything is typed, every exit asks first.
  describe("accidental dismissal", () => {
    it("keeps the typed form when the backdrop is clicked", async () => {
      renderWithQuery(<EventsSection />);
      fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
      fireEvent.change(await screen.findByLabelText(/School/i), {
        target: { value: "Goleta Valley Junior High" },
      });

      fireEvent.mouseDown(screen.getByTestId("form-modal-backdrop"));

      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
      expect(screen.getByLabelText(/School/i)).toHaveValue(
        "Goleta Valley Junior High",
      );
    });

    it("closes without asking while the form is untouched", async () => {
      renderWithQuery(<EventsSection />);
      fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
      await screen.findByTestId("shift-row-0");

      fireEvent.mouseDown(screen.getByTestId("form-modal-backdrop"));

      expect(screen.queryByText("Discard changes?")).toBeNull();
      expect(screen.queryByTestId("shift-row-0")).not.toBeInTheDocument();
    });

    it("discards the form once confirmed", async () => {
      renderWithQuery(<EventsSection />);
      fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
      fireEvent.change(await screen.findByLabelText(/School/i), {
        target: { value: "Goleta Valley Junior High" },
      });

      fireEvent.mouseDown(screen.getByTestId("form-modal-backdrop"));
      fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));

      expect(screen.queryByTestId("shift-row-0")).not.toBeInTheDocument();
    });

    // Reopening after a discard must not inherit the last session's dirtiness.
    it("does not ask on a freshly reopened form", async () => {
      renderWithQuery(<EventsSection />);
      fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
      fireEvent.change(await screen.findByLabelText(/School/i), {
        target: { value: "Goleta Valley Junior High" },
      });
      fireEvent.mouseDown(screen.getByTestId("form-modal-backdrop"));
      fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));

      fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
      await screen.findByTestId("shift-row-0");
      fireEvent.mouseDown(screen.getByTestId("form-modal-backdrop"));

      expect(screen.queryByText("Discard changes?")).toBeNull();
      expect(screen.queryByTestId("shift-row-0")).not.toBeInTheDocument();
    });
  });

  it("add and remove shift buttons update the list", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^Add shift$/i }));
    expect(screen.getByTestId("shift-row-1")).toBeInTheDocument();

    const row1 = screen.getByTestId("shift-row-1");
    // Exact match: the session rows inside also have Remove buttons.
    fireEvent.click(within(row1).getByRole("button", { name: /^Remove$/i }));
    expect(screen.queryByTestId("shift-row-1")).not.toBeInTheDocument();
  });

  it("add and remove orientation slot buttons update the list", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /^Add orientation slot$/i }),
    );
    expect(screen.getByTestId("slot-row-0")).toBeInTheDocument();

    const row0 = screen.getByTestId("slot-row-0");
    fireEvent.click(within(row0).getByRole("button", { name: /Remove/i }));
    expect(screen.queryByTestId("slot-row-0")).not.toBeInTheDocument();
  });

  // A shift's sessions are added and reordered inside the shift — capacity is
  // the shift's, so a session row never has one.
  it("adds, reorders and removes sessions inside a shift", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));
    await screen.findByTestId("shift-row-0");

    // The last session cannot be removed — a shift must keep one.
    expect(
      screen.getByRole("button", { name: /Remove shift 1 session 1/i }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /^Add session$/i }));
    expect(screen.getByTestId("shift-0-session-1")).toBeInTheDocument();

    fireEvent.change(
      screen.getByLabelText(/Shift 1 session 1 name/i),
      { target: { value: "First" } },
    );
    fireEvent.change(
      screen.getByLabelText(/Shift 1 session 2 name/i),
      { target: { value: "Second" } },
    );

    fireEvent.click(screen.getByRole("button", { name: /Move shift 1 session 2 up/i }));
    expect(screen.getByLabelText(/Shift 1 session 1 name/i)).toHaveValue("Second");
    expect(screen.getByLabelText(/Shift 1 session 2 name/i)).toHaveValue("First");

    fireEvent.click(
      screen.getByRole("button", { name: /Remove shift 1 session 2/i }),
    );
    expect(screen.queryByTestId("shift-0-session-1")).not.toBeInTheDocument();
  });

  // Native time inputs ignore the wheel entirely, but admins set dozens of
  // slot times per sitting — so the field steps on scroll once focused.
  it("steps a slot time with the mouse wheel while focused", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /\+ New event/i }));

    const start = await screen.findByLabelText(/Shift 1 session 1 start time/i);
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

    const start = await screen.findByLabelText(/Shift 1 session 1 start time/i);
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

    const start = await screen.findByLabelText(/Shift 1 session 1 start time/i);
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

    fireEvent.click(screen.getByRole("button", { name: /^Add orientation slot$/i }));
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

  it("submits a create payload with shifts and orientation slots", async () => {
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

    // The shift and its one session — this is the bookable unit.
    fireEvent.change(screen.getByLabelText(/Shift 1 name/i), {
      target: { value: "Tue 1:00pm" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 1 capacity/i), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 1 session 1 name/i), {
      target: { value: "Period 1" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 1 session 1 date/i), {
      target: { value: "2026-04-20" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 1 session 1 start time/i), {
      target: { value: "10:00" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 1 session 1 end time/i), {
      target: { value: "11:00" },
    });

    // Plus one orientation slot, which keeps its own capacity.
    fireEvent.click(screen.getByRole("button", { name: /^Add orientation slot$/i }));
    const row = screen.getByTestId("slot-row-0");
    fireEvent.change(within(row).getByLabelText(/Slot 1 date/i), {
      target: { value: "2026-04-20" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 start time/i), {
      target: { value: "08:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 end time/i), {
      target: { value: "09:00" },
    });
    fireEvent.change(within(row).getByLabelText(/Slot 1 capacity/i), {
      target: { value: "20" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => expect(api.events.create).toHaveBeenCalledTimes(1));
    const payload = api.events.create.mock.calls[0][0];
    expect(payload.title).toBe("Science Fair");
    expect(payload.module_slug).toBe("crispr-intro");
    expect(payload.slots).toHaveLength(1);
    expect(payload.slots[0].capacity).toBe(20);
    expect(payload.slots[0].slot_type).toBe("orientation");
    expect(payload.shifts).toHaveLength(1);
    expect(payload.shifts[0].name).toBe("Tue 1:00pm");
    expect(payload.shifts[0].capacity).toBe(12);
    expect(payload.shifts[0].sort_order).toBe(0);
    expect(payload.shifts[0].sessions).toHaveLength(1);
    expect(payload.shifts[0].sessions[0].name).toBe("Period 1");
    expect(payload.shifts[0].sessions[0].start_time).toMatch(/^2026-04-20T/);
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
    // The module check fires before anything shift- or slot-shaped is looked
    // at, so the rest of the form is irrelevant here.
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
    api.shifts.create.mockResolvedValue({});
    api.shifts.update.mockResolvedValue({});
    api.shifts.delete.mockResolvedValue({});
    api.shifts.addSession.mockResolvedValue({});
    api.shifts.updateSession.mockResolvedValue({});
    api.shifts.deleteSession.mockResolvedValue({});
    api.admin.modules.list.mockResolvedValue(FIXTURE_MODULES);
  });

  it("renders the orientation slot and the shift, each with its signup count", async () => {
    renderWithQuery(<EventsSection />);
    // FIXTURE_EVENT is dated in the past, but the default scope is now
    // "All" so the row (and its Edit button) is visible immediately.
    fireEvent.click(await screen.findByRole("button", { name: /^Edit$/i }));

    // One orientation row — the period slot belongs to the shift, so it is
    // not offered as an independently editable row.
    expect(await screen.findByTestId("slot-row-0")).toBeInTheDocument();
    expect(screen.queryByTestId("slot-row-1")).not.toBeInTheDocument();

    const shiftRow = screen.getByTestId("shift-row-0");
    expect(within(shiftRow).getByLabelText(/Shift 1 name/i)).toHaveValue("Tue 1:00pm");
    expect(within(shiftRow).getByLabelText(/Shift 1 capacity/i)).toHaveValue(30);
    // shift-1 has 5 signups, so Remove is refused here as well as server-side.
    expect(within(shiftRow).getByRole("button", { name: /^Remove$/i })).toBeDisabled();
    expect(within(shiftRow).getByText(/5 signups/i)).toBeInTheDocument();
  });

  it("shows a shift's sessions only once expanded", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /^Edit$/i }));
    await screen.findByTestId("shift-row-0");

    expect(screen.queryByTestId("shift-0-session-0")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Show 1 session/i }));
    expect(screen.getByTestId("shift-0-session-0")).toBeInTheDocument();
    expect(screen.getByLabelText(/Shift 1 session 1 name/i)).toHaveValue("Period 1");
    expect(screen.getByLabelText(/Shift 1 session 1 location/i)).toHaveValue("Hall B");
  });

  it("issues PATCH for changed capacity, POST for new slot, DELETE for removed", async () => {
    // Override: drop the shift's signups so its session can be edited and a
    // second orientation slot removed in this test.
    const editable = {
      ...FIXTURE_EVENT,
      slots: [
        { ...FIXTURE_EVENT.slots[0] },
        {
          ...FIXTURE_EVENT.slots[0],
          id: "slot-3",
          start_time: "2026-04-20T14:00:00Z",
          end_time: "2026-04-20T15:00:00Z",
        },
        FIXTURE_EVENT.slots[1],
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

    // remove row 1 (existing slot-3) → DELETE
    fireEvent.click(
      within(screen.getByTestId("slot-row-1")).getByRole("button", { name: /^Remove$/i }),
    );

    // add a new orientation slot → POST
    fireEvent.click(screen.getByRole("button", { name: /^Add orientation slot$/i }));
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
    expect(api.slots.delete).toHaveBeenCalledWith("slot-3");
    expect(api.slots.create.mock.calls[0][0]).toBe("evt-1");
    expect(api.slots.create.mock.calls[0][1].capacity).toBe(15);
    // Nothing about the shift moved, so it is left alone.
    expect(api.shifts.update).not.toHaveBeenCalled();
  });

  it("PATCHes the shift when its capacity changes and leaves slots alone", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /^Edit$/i }));
    await screen.findByTestId("shift-row-0");

    fireEvent.change(screen.getByLabelText(/Shift 1 capacity/i), {
      target: { value: "45" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => expect(api.shifts.update).toHaveBeenCalledTimes(1));
    expect(api.shifts.update.mock.calls[0][0]).toBe("shift-1");
    expect(api.shifts.update.mock.calls[0][1]).toEqual({
      name: "Tue 1:00pm",
      capacity: 45,
      sort_order: 0,
    });
    expect(api.slots.update).not.toHaveBeenCalled();
    expect(api.slots.create).not.toHaveBeenCalled();
  });

  it("PATCHes a session through its own endpoint when its time moves", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /^Edit$/i }));
    await screen.findByTestId("shift-row-0");

    fireEvent.click(screen.getByRole("button", { name: /Show 1 session/i }));
    fireEvent.change(screen.getByLabelText(/Shift 1 session 1 start time/i), {
      target: { value: "13:00" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 1 session 1 end time/i), {
      target: { value: "14:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => expect(api.shifts.updateSession).toHaveBeenCalledTimes(1));
    expect(api.shifts.updateSession.mock.calls[0][0]).toBe("slot-2");
    expect(api.shifts.updateSession.mock.calls[0][1].start_time).toMatch(
      /^2026-04-20T/,
    );
    expect(api.shifts.updateSession.mock.calls[0][1].sort_order).toBe(0);
    // Capacity is the shift's, so a session PATCH never carries one.
    expect(api.shifts.updateSession.mock.calls[0][1].capacity).toBeUndefined();
    expect(api.shifts.update).not.toHaveBeenCalled();
  });

  it("POSTs a whole shift when a new one is added", async () => {
    renderWithQuery(<EventsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /^Edit$/i }));
    await screen.findByTestId("shift-row-0");

    fireEvent.click(screen.getByRole("button", { name: /^Add shift$/i }));
    fireEvent.change(screen.getByLabelText(/Shift 2 name/i), {
      target: { value: "Wed 10:00am" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 2 capacity/i), {
      target: { value: "8" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 2 session 1 date/i), {
      target: { value: "2026-04-20" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 2 session 1 start time/i), {
      target: { value: "10:00" },
    });
    fireEvent.change(screen.getByLabelText(/Shift 2 session 1 end time/i), {
      target: { value: "11:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => expect(api.shifts.create).toHaveBeenCalledTimes(1));
    expect(api.shifts.create.mock.calls[0][0]).toBe("evt-1");
    const created = api.shifts.create.mock.calls[0][1];
    expect(created.name).toBe("Wed 10:00am");
    expect(created.capacity).toBe(8);
    expect(created.sort_order).toBe(1);
    expect(created.sessions).toHaveLength(1);
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

// ---------------------------------------------------------------------------
// K14 — the delete-event dialog
//
// This was a bare <div>: no role="dialog", no Escape, no focus trap, and a
// single click on a red button. It destroys the event, its slots and shifts,
// and every signup on them — while module *archive*, which is undone with one
// click, got the real accessible Modal. The guard now matches the damage.
// ---------------------------------------------------------------------------

describe("EventsSection — deleting an event (K14)", () => {
  const LIVE_Q = {
    id: "q-live",
    display_name: "Fall 2026",
    season: "fall",
    year: 2026,
    start_date: "2026-09-21",
    end_date: "2026-12-11",
    archived_at: null,
  };

  function renderSection() {
    window.localStorage.setItem("admin.selectedQuarterId", "q-live");
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
    api.public.getQuarters.mockResolvedValue([LIVE_Q]);
    api.events.list.mockResolvedValue([
      {
        id: "e-doomed",
        title: "Germs at Goleta Valley",
        start_date: "2026-10-06T15:00:00Z",
        end_date: "2026-10-06T19:00:00Z",
        completed_at: null,
        location: "Room 4",
      },
    ]);
    api.admin.modules.list.mockResolvedValue([]);
    api.events.delete.mockResolvedValue({});
    // mockResolvedValue does not reset the call log, and "we never deleted"
    // is the assertion most of these tests turn on.
    api.events.delete.mockClear();
  });

  async function openDeleteDialog() {
    renderSection();
    await screen.findByText("Germs at Goleta Valley");
    // findBy, not getBy. The row title arrives on the first events fetch, but
    // QuarterSelectionProvider resolves its quarter list a tick later and the
    // list re-queries, so the table is briefly empty again *after* the title
    // has appeared. A synchronous getBy here landed in that window roughly
    // one run in six and failed looking for a Delete button that was about
    // to come back.
    fireEvent.click(await screen.findByRole("button", { name: /^Delete$/i }));
    return screen.findByRole("dialog", { name: /delete this event/i });
  }

  it("opens a real dialog rather than a bare div", async () => {
    const dialog = await openDeleteDialog();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(api.events.delete).not.toHaveBeenCalled();
  });

  it("says what actually goes, including the signups", async () => {
    const dialog = await openDeleteDialog();
    expect(dialog).toHaveTextContent("Germs at Goleta Valley");
    expect(dialog).toHaveTextContent(/every signup/i);
    expect(dialog).toHaveTextContent(/cannot be undone/i);
  });

  it("keeps the confirm button disabled until the title is typed exactly", async () => {
    const dialog = await openDeleteDialog();
    const confirm = within(dialog).getByRole("button", { name: /delete event/i });
    expect(confirm).toBeDisabled();

    // A near miss must not arm it — the whole point is that the operator has
    // to read which event this is.
    fireEvent.change(within(dialog).getByLabelText(/type the event title/i), {
      target: { value: "Germs at Goleta" },
    });
    expect(confirm).toBeDisabled();
    expect(api.events.delete).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText(/type the event title/i), {
      target: { value: "Germs at Goleta Valley" },
    });
    expect(confirm).toBeEnabled();
  });

  it("deletes only after the typed confirmation", async () => {
    const dialog = await openDeleteDialog();
    fireEvent.change(within(dialog).getByLabelText(/type the event title/i), {
      target: { value: "Germs at Goleta Valley" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /delete event/i }));

    await waitFor(() =>
      expect(api.events.delete).toHaveBeenCalledWith("e-doomed"),
    );
  });

  it("forgets what was typed when the dialog is dismissed and reopened", async () => {
    const dialog = await openDeleteDialog();
    fireEvent.change(within(dialog).getByLabelText(/type the event title/i), {
      target: { value: "Germs at Goleta Valley" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /keep it/i }));

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: /delete this event/i }),
      ).toBeNull(),
    );

    const reopened = await openDeleteDialog();
    expect(
      within(reopened).getByRole("button", { name: /delete event/i }),
    ).toBeDisabled();
    expect(api.events.delete).not.toHaveBeenCalled();
  });
});
