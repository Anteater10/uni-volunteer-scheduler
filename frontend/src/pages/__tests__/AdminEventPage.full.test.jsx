// AdminEventPage.full.test.jsx — every state and action on the admin event
// page: loading/error states, details, form fields, the grouped roster and each
// row action, waitlist reorder, CSV export, reopen, and the header buttons.

import React from "react";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockUser = { role: "admin" };

vi.mock("../../lib/api", () => {
  const apiMock = {
    admin: {
      eventAnalytics: vi.fn(),
      eventRoster: vi.fn(),
      signups: { cancel: vi.fn(), uncancel: vi.fn() },
      shiftSignups: { cancel: vi.fn(), uncancel: vi.fn() },
      reorderWaitlist: vi.fn(),
      reorderShiftWaitlist: vi.fn(),
      setEventFormSchema: vi.fn(),
      addVolunteer: vi.fn(),
    },
    organizer: {
      grantOrientation: vi.fn(),
      grantOrientationForShift: vi.fn(),
      promoteSignup: vi.fn(),
      promoteShiftSignup: vi.fn(),
    },
    events: { get: vi.fn() },
    public: { getQuarters: vi.fn(), getFormSchema: vi.fn() },
  };
  return { api: apiMock, default: apiMock, downloadBlob: vi.fn() };
});
vi.mock("../../state/toast", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("../../state/useAuth", () => ({ useAuth: () => ({ user: mockUser }) }));
vi.mock("../admin/AdminLayout", () => ({ useAdminPageTitle: vi.fn() }));
vi.mock("../../api/roster", () => ({ reopenEvent: vi.fn() }));

// Child modals are stubs that show they are open and expose their callbacks.
function stub(testId) {
  return {
    default: ({ open, onClose, onSave, scope }) =>
      open ? (
        <div data-testid={testId} data-scope={scope}>
          <button onClick={onClose}>close {testId}</button>
          {onSave ? <button onClick={() => onSave([{ id: "f" }])}>save {testId}</button> : null}
        </div>
      ) : null,
  };
}
vi.mock("../../components/admin/FormFieldsDrawer", () => stub("form-fields"));
vi.mock("../../components/admin/EventSettingsModal", () => stub("settings"));
vi.mock("../../components/admin/DuplicateEventModal", () => stub("duplicate"));
vi.mock("../../components/BroadcastModal", () => stub("broadcast"));
vi.mock("../../components/admin/CheckInQRModal", () => stub("checkin-qr"));
vi.mock("../../components/admin/SignupQRModal", () => stub("signup-qr"));
vi.mock("../../components/admin/AddVolunteerModal", () => stub("add-volunteer"));

import { api, downloadBlob } from "../../lib/api";
import { toast } from "../../state/toast";
import { reopenEvent } from "../../api/roster";
import { useAdminPageTitle } from "../admin/AdminLayout";
import AdminEventPage from "../AdminEventPage";

const ACTIVE_QUARTER = {
  id: "q-active",
  display_name: "Fall 2026",
  archived_at: null,
  start_date: new Date(Date.now() - 30 * 86400e3).toISOString().slice(0, 10),
  end_date: new Date(Date.now() + 30 * 86400e3).toISOString().slice(0, 10),
};

const EVENT = {
  id: "evt-1",
  title: "Conservation of Mass",
  location: "Chem 1204",
  visibility: "public",
  start_date: "2026-10-20T17:00:00Z",
  end_date: "2026-10-22T20:00:00Z",
  max_signups_per_user: 2,
  created_at: "2026-09-01T00:00:00Z",
  description: "Bring goggles.",
  completed_at: null,
  quarter_id: "q-active",
};

const ANALYTICS = {
  title: "From analytics",
  total_slots: 4,
  total_capacity: 20,
  confirmed_signups: 3,
  waitlisted_signups: 2,
};

function orientRow(over = {}) {
  return {
    signup_id: "o1",
    is_shift: false,
    slot_id: "slot-o",
    slot_type: "orientation",
    slot_start: "2026-10-06T23:00:00Z",
    slot_end: "2026-10-07T01:00:00Z",
    slot_location: "Chem 1005D",
    status: "confirmed",
    participant: { name: "Ana Diaz", email: "ana@x.com", phone: "+18055551234" },
    no_show_count: 0,
    responses: [],
    ...over,
  };
}

function shiftRow(over = {}) {
  return {
    signup_id: "ss1",
    is_shift: true,
    shift_id: "sh1",
    shift_name: "Tue + Thu P1",
    slot_id: "sess-1",
    session_name: "Shift 1- T",
    slot_type: "period",
    slot_start: "2026-10-20T17:23:00Z",
    slot_end: "2026-10-20T19:13:00Z",
    slot_location: "Room 12",
    status: "confirmed",
    participant: { name: "Sam Lee", email: "sam@x.com" },
    no_show_count: 0,
    responses: [],
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin/events/evt-1"]}>
        <Routes>
          <Route path="/admin/events/:eventId" element={<AdminEventPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.role = "admin";
  api.admin.eventAnalytics.mockResolvedValue(ANALYTICS);
  api.events.get.mockResolvedValue(EVENT);
  api.admin.eventRoster.mockResolvedValue([]);
  api.public.getQuarters.mockResolvedValue([ACTIVE_QUARTER]);
  api.public.getFormSchema.mockResolvedValue({ schema: [] });
  window.confirm = vi.fn(() => true);
});

describe("loading and error states", () => {
  it("shows skeletons while loading", () => {
    api.admin.eventAnalytics.mockReturnValue(new Promise(() => {}));
    api.events.get.mockReturnValue(new Promise(() => {}));
    api.admin.eventRoster.mockReturnValue(new Promise(() => {}));
    api.public.getFormSchema.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    expect(container.querySelectorAll(".animate-pulse, [class*='skeleton' i]").length).toBeGreaterThan(0);
    expect(useAdminPageTitle).toHaveBeenLastCalledWith("Event");
  });

  it("offers Try again on each failed section", async () => {
    api.admin.eventAnalytics.mockRejectedValue(new Error("analytics down"));
    api.events.get.mockRejectedValue(new Error("event down"));
    api.admin.eventRoster.mockRejectedValue(new Error("roster down"));
    renderPage();
    expect(await screen.findByText("Couldn't load attendance summary")).toBeInTheDocument();
    expect(await screen.findByText("Couldn't load event")).toBeInTheDocument();
    expect(await screen.findByText("Couldn't load roster")).toBeInTheDocument();

    api.admin.eventAnalytics.mockResolvedValue(ANALYTICS);
    api.events.get.mockResolvedValue(EVENT);
    api.admin.eventRoster.mockResolvedValue([]);
    for (const b of screen.getAllByRole("button", { name: /try again/i })) {
      await userEvent.click(b);
    }
    expect(await screen.findByText("Bring goggles.")).toBeInTheDocument();
    expect(await screen.findByText("No one has signed up yet")).toBeInTheDocument();
  });

  it("falls back to the analytics title when the event has none", async () => {
    api.events.get.mockResolvedValue({ ...EVENT, title: "" });
    renderPage();
    await waitFor(() => expect(useAdminPageTitle).toHaveBeenLastCalledWith("From analytics"));
  });
});

describe("details and stats", () => {
  it("renders stats and every detail row", async () => {
    renderPage();
    expect(await screen.findByText("Bring goggles.")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(screen.getByText("Chem 1204")).toBeInTheDocument();
    const maxRow = screen.getByText("Max shifts per volunteer").parentElement;
    expect(within(maxRow).getByText("2")).toBeInTheDocument();
  });

  it("uses dashes and No limit for missing values", async () => {
    api.events.get.mockResolvedValue({
      ...EVENT, location: "", visibility: "", max_signups_per_user: null, description: "",
    });
    api.admin.eventAnalytics.mockResolvedValue({ ...ANALYTICS, total_slots: null });
    renderPage();
    expect(await screen.findByText("No limit")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("Description")).not.toBeInTheDocument();
  });
});

describe("form fields", () => {
  it("lists questions with required badges and saves from the drawer", async () => {
    api.public.getFormSchema.mockResolvedValue({
      schema: [
        { id: "shirt", label: "Shirt size", type: "select", required: true },
        { id: "diet", label: "Diet", type: "text" },
      ],
    });
    api.admin.setEventFormSchema.mockResolvedValue({});
    renderPage();
    expect(await screen.findByText("2 questions on this event's signup form.")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    await userEvent.click(screen.getByRole("button", { name: /save form-fields/i }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Form fields saved"));
    expect(api.admin.setEventFormSchema).toHaveBeenCalledWith("evt-1", [{ id: "f" }]);
    await waitFor(() => expect(screen.queryByTestId("form-fields")).not.toBeInTheDocument());
  });

  it("says 1 question in the singular and reports a failed save", async () => {
    api.public.getFormSchema.mockResolvedValue({ schema: [{ id: "a", label: "A", type: "text" }] });
    api.admin.setEventFormSchema.mockRejectedValueOnce(new Error("bad schema")).mockRejectedValueOnce({});
    renderPage();
    expect(await screen.findByText("1 question on this event's signup form.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    await userEvent.click(screen.getByRole("button", { name: /save form-fields/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("bad schema"));
    await userEvent.click(screen.getByRole("button", { name: /save form-fields/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Save failed"));
    await userEvent.click(screen.getByRole("button", { name: /close form-fields/i }));
    expect(screen.queryByTestId("form-fields")).not.toBeInTheDocument();
  });

  it("offers Add a question when the schema is missing", async () => {
    api.public.getFormSchema.mockResolvedValue({});
    renderPage();
    expect(await screen.findByRole("button", { name: /add a question/i })).toBeInTheDocument();
  });
});

describe("roster rendering", () => {
  it("groups shifts first, collapses sessions, and labels slots", async () => {
    api.admin.eventRoster.mockResolvedValue([
      orientRow({ slot_location: null }),
      orientRow({ signup_id: "m1", slot_id: "slot-m", slot_type: "period", slot_location: "Lab" }),
      shiftRow(),
      shiftRow({ slot_id: "sess-2", session_name: null, slot_start: "2026-10-22T17:23:00Z", slot_location: null, status: "attended" }),
      shiftRow({ signup_id: "ss2", shift_id: "sh2", shift_name: null, slot_id: "sess-3", status: "waitlisted", waitlist_position: 1, participant: { email: "only@x.com" } }),
    ]);
    renderPage();
    const shift1 = await screen.findByTestId("roster-shift-sh1");
    expect(within(shift1).getByText("Tue + Thu P1")).toBeInTheDocument();
    expect(within(shift1).getByText(/2 sessions/)).toBeInTheDocument();
    expect(within(shift1).getByText(/Shift 1- T —/)).toBeInTheDocument();
    // One row for the commitment, even though it has two session rows.
    expect(within(shift1).getAllByText("Sam Lee")).toHaveLength(1);

    const shift2 = screen.getByTestId("roster-shift-sh2");
    expect(within(shift2).getByText("Untitled shift")).toBeInTheDocument();
    expect(within(shift2).getByText(/1 session$/)).toBeInTheDocument();
    expect(within(shift2).getByText("only@x.com")).toBeInTheDocument();
    expect(within(shift2).getByText("Waitlist #1")).toBeInTheDocument();

    expect(within(screen.getByTestId("roster-slot-slot-o")).getByText("Orientation")).toBeInTheDocument();
    expect(within(screen.getByTestId("roster-slot-slot-m")).getByText("Module")).toBeInTheDocument();
    expect(within(screen.getByTestId("roster-slot-slot-m")).getByText(/Lab/)).toBeInTheDocument();
  });

  it("orders shift groups by their first session", async () => {
    api.admin.eventRoster.mockResolvedValue([
      shiftRow({ shift_id: "late", signup_id: "a", slot_id: "x", slot_start: "2026-10-22T17:00:00Z" }),
      shiftRow({ shift_id: "early", signup_id: "b", slot_id: "y", slot_start: "2026-10-20T17:00:00Z" }),
    ]);
    renderPage();
    await screen.findByTestId("roster-shift-late");
    const ids = screen.getAllByTestId(/roster-shift-/).map((el) => el.dataset.testid);
    expect(ids).toEqual(["roster-shift-early", "roster-shift-late"]);
  });

  it.each([
    [["confirmed", "cancelled"], "cancelled"],
    [["pending", "attended"], "pending"],
    [["attended", "no_show"], "confirmed"],
  ])("commitment status from sessions %j is %s", async (statuses, expected) => {
    api.admin.eventRoster.mockResolvedValue(
      statuses.map((status, i) => shiftRow({ slot_id: `s${i}`, status })),
    );
    renderPage();
    const group = await screen.findByTestId("roster-shift-sh1");
    expect(within(group).getByText(expected)).toBeInTheDocument();
  });

  it("shows contact details, responses and a status fallback", async () => {
    api.admin.eventRoster.mockResolvedValue([
      orientRow({
        responses: [
          { field_id: "a", label: "Shirt", value_text: "M" },
          { field_id: "b", label: "Days", value_json: ["Tue"] },
          { field_id: "c", label: "Blank" },
        ],
      }),
      orientRow({ signup_id: "o2", participant: { name: "Intl", phone: "+442071234567" }, status: "mystery_status" }),
      orientRow({ signup_id: "o3", participant: {}, status: undefined }),
    ]);
    renderPage();
    expect(await screen.findByText("(805) 555-1234")).toHaveAttribute("href", "tel:+18055551234");
    expect(screen.getByText("ana@x.com")).toBeInTheDocument();
    expect(screen.getByText("M")).toBeInTheDocument();
    expect(screen.getByText('["Tue"]')).toBeInTheDocument();
    expect(screen.getByText("+442071234567")).toBeInTheDocument();
    expect(screen.getByText("mystery status")).toBeInTheDocument();
    // A participant with neither name nor email reads as "Volunteer".
    expect(screen.getAllByRole("cell", { name: /^Volunteer$/ })).toHaveLength(1);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("remaining display states", () => {
  it("shows dashes for a row with no times", async () => {
    api.admin.eventRoster.mockResolvedValue([orientRow({ slot_start: null, slot_end: null })]);
    renderPage();
    const group = await screen.findByTestId("roster-slot-slot-o");
    expect(within(group).getAllByText(/—/).length).toBeGreaterThan(0);
  });

  it("shows a start time alone when there is no end", async () => {
    api.admin.eventRoster.mockResolvedValue([orientRow({ slot_end: null })]);
    renderPage();
    const group = await screen.findByTestId("roster-slot-slot-o");
    expect(within(group).queryByText(/–/)).not.toBeInTheDocument();
  });

  it("labels Reopen and Save order while they are in flight", async () => {
    api.events.get.mockResolvedValue({ ...EVENT, completed_at: "2026-10-22T21:00:00Z" });
    reopenEvent.mockReturnValue(new Promise(() => {}));
    api.admin.eventRoster.mockResolvedValue([
      orientRow({ signup_id: "a", status: "waitlisted", waitlist_position: null }),
      orientRow({ signup_id: "b", status: "waitlisted", waitlist_position: null }),
    ]);
    api.admin.reorderWaitlist.mockReturnValue(new Promise(() => {}));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /reopen event/i }));
    expect(await screen.findByRole("button", { name: /reopening/i })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /reorder waitlist/i }));
    await userEvent.click(screen.getByRole("button", { name: /save order/i }));
    expect(await screen.findByRole("button", { name: /saving/i })).toBeDisabled();
    // Escape is ignored while the save is in flight.
    await userEvent.keyboard("{Escape}");
    expect(screen.getByTestId("reorder-modal")).toBeInTheDocument();
  });

  it("closes the export dialog with Escape", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /roster csv/i }));
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("row actions", () => {
  it("promotes a waitlisted slot signup", async () => {
    api.admin.eventRoster.mockResolvedValue([orientRow({ status: "waitlisted" })]);
    api.organizer.promoteSignup.mockResolvedValue({});
    renderPage();
    await userEvent.click(await screen.findByTestId("promote-btn"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Promoted from waitlist."));
    expect(api.organizer.promoteSignup).toHaveBeenCalledWith("evt-1", "o1", { allowOverfill: false });
  });

  it("offers to overfill a full shift and retries when confirmed", async () => {
    api.admin.eventRoster.mockResolvedValue([shiftRow({ status: "waitlisted" })]);
    api.organizer.promoteShiftSignup
      .mockRejectedValueOnce(new Error("Shift is full"))
      .mockResolvedValueOnce({});
    renderPage();
    await userEvent.click(await screen.findByTestId("promote-btn"));
    await waitFor(() => expect(api.organizer.promoteShiftSignup).toHaveBeenCalledTimes(2));
    expect(window.confirm.mock.calls[0][0]).toMatch(/This shift is already at capacity/);
    expect(api.organizer.promoteShiftSignup).toHaveBeenLastCalledWith("evt-1", "ss1", { allowOverfill: true });
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("does nothing more when overfill is declined", async () => {
    window.confirm = vi.fn(() => false);
    api.admin.eventRoster.mockResolvedValue([orientRow({ status: "waitlisted" })]);
    api.organizer.promoteSignup.mockRejectedValue(new Error("Slot is full"));
    renderPage();
    await userEvent.click(await screen.findByTestId("promote-btn"));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    expect(window.confirm.mock.calls[0][0]).toMatch(/This slot is already at capacity/);
    expect(api.organizer.promoteSignup).toHaveBeenCalledTimes(1);
  });

  it("reports a promote failure that is not about capacity", async () => {
    api.admin.eventRoster.mockResolvedValue([orientRow({ status: "waitlisted" })]);
    api.organizer.promoteSignup.mockRejectedValueOnce(new Error("Session ended"));
    renderPage();
    await userEvent.click(await screen.findByTestId("promote-btn"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Session ended"));
    expect(window.confirm).not.toHaveBeenCalled();
  });

  it("uses a generic message when promote fails without one", async () => {
    api.admin.eventRoster.mockResolvedValue([orientRow({ status: "waitlisted" })]);
    api.organizer.promoteSignup.mockRejectedValueOnce({});
    renderPage();
    await userEvent.click(await screen.findByTestId("promote-btn"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Promote failed"));
  });

  it("grants orientation for slot and shift rows, and reports failures", async () => {
    api.admin.eventRoster.mockResolvedValue([orientRow(), shiftRow()]);
    api.organizer.grantOrientation.mockResolvedValue({});
    api.organizer.grantOrientationForShift.mockRejectedValueOnce(new Error("nope")).mockRejectedValueOnce({});
    renderPage();
    const [shiftBtn, slotBtn] = await screen.findAllByRole("button", { name: /grant orientation/i });
    await userEvent.click(slotBtn);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Orientation credit granted."));
    expect(api.organizer.grantOrientation).toHaveBeenCalledWith("evt-1", "o1");
    await userEvent.click(shiftBtn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("nope"));
    await userEvent.click(shiftBtn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Grant failed"));
  });

  it("cancels after confirming, for slot and shift rows", async () => {
    api.admin.eventRoster.mockResolvedValue([orientRow(), shiftRow()]);
    api.admin.signups.cancel.mockResolvedValue({});
    api.admin.shiftSignups.cancel.mockRejectedValueOnce(new Error("has attendance")).mockRejectedValueOnce({});
    renderPage();
    const [shiftCancel, slotCancel] = await screen.findAllByRole("button", { name: /^cancel$/i });
    await userEvent.click(slotCancel);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Signup cancelled."));
    await userEvent.click(shiftCancel);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("has attendance"));
    await userEvent.click(shiftCancel);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Cancel failed"));
  });

  it("does not cancel when the confirm is declined", async () => {
    window.confirm = vi.fn(() => false);
    api.admin.eventRoster.mockResolvedValue([orientRow()]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /^cancel$/i }));
    expect(api.admin.signups.cancel).not.toHaveBeenCalled();
  });

  it("reinstates cancelled rows after confirming, and reports failures", async () => {
    api.admin.eventRoster.mockResolvedValue([
      orientRow({ status: "cancelled" }),
      shiftRow({ status: "cancelled" }),
    ]);
    api.admin.signups.uncancel.mockResolvedValue({});
    api.admin.shiftSignups.uncancel.mockRejectedValueOnce(new Error("full")).mockRejectedValueOnce({});
    renderPage();
    const [shiftBtn, slotBtn] = await screen.findAllByRole("button", { name: /uncancel/i });
    expect(screen.queryByRole("button", { name: /grant orientation/i })).not.toBeInTheDocument();
    await userEvent.click(slotBtn);
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Signup reinstated. The volunteer has been emailed."),
    );
    await userEvent.click(shiftBtn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("full"));
    await userEvent.click(shiftBtn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Reinstate failed"));
  });

  it("does not reinstate when the confirm is declined", async () => {
    window.confirm = vi.fn(() => false);
    api.admin.eventRoster.mockResolvedValue([orientRow({ status: "cancelled" })]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /uncancel/i }));
    expect(api.admin.signups.uncancel).not.toHaveBeenCalled();
  });
});

describe("waitlist reorder", () => {
  const waitlist = [
    orientRow({ signup_id: "w2", status: "waitlisted", waitlist_position: 2, participant: { name: "Second" } }),
    orientRow({ signup_id: "w1", status: "waitlisted", waitlist_position: 1, participant: { name: "First" } }),
    orientRow({ signup_id: "w3", status: "waitlisted", waitlist_position: null, participant: { name: "Unranked" } }),
  ];

  it("names each volunteer, reorders, and saves a slot waitlist", async () => {
    api.admin.eventRoster.mockResolvedValue(waitlist);
    api.admin.reorderWaitlist.mockResolvedValue({});
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /reorder waitlist/i }));
    const modal = screen.getByTestId("reorder-modal");
    const items = () => within(modal).getAllByRole("listitem").map((li) => li.textContent);
    expect(items()[0]).toMatch(/#1 Unranked/);
    expect(items()[1]).toMatch(/#2 First/);

    const downs = within(modal).getAllByRole("button", { name: /move down/i });
    expect(downs[2]).toBeDisabled();
    await userEvent.click(downs[0]);
    await userEvent.click(within(modal).getAllByRole("button", { name: /move up/i })[2]);
    expect(within(modal).getAllByRole("button", { name: /move up/i })[0]).toBeDisabled();

    await userEvent.click(within(modal).getByRole("button", { name: /save order/i }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Waitlist order saved."));
    expect(api.admin.reorderWaitlist).toHaveBeenCalledWith("evt-1", "slot-o", ["w1", "w2", "w3"]);
    await waitFor(() => expect(screen.queryByTestId("reorder-modal")).not.toBeInTheDocument());
  });

  it("reorders a shift waitlist through the shift route and reports failures", async () => {
    api.admin.eventRoster.mockResolvedValue([
      shiftRow({ signup_id: "a", status: "waitlisted", waitlist_position: 1 }),
      shiftRow({ signup_id: "b", status: "waitlisted", waitlist_position: 2 }),
    ]);
    api.admin.reorderShiftWaitlist.mockRejectedValueOnce(new Error("stale")).mockRejectedValueOnce({});
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /reorder waitlist/i }));
    const save = within(screen.getByTestId("reorder-modal")).getByRole("button", { name: /save order/i });
    await userEvent.click(save);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("stale"));
    expect(api.admin.reorderShiftWaitlist).toHaveBeenCalledWith("evt-1", "sh1", ["a", "b"]);
    await userEvent.click(save);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Reorder failed"));
  });

  it("closes with Cancel or Escape", async () => {
    api.admin.eventRoster.mockResolvedValue(waitlist);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /reorder waitlist/i }));
    await userEvent.click(within(screen.getByTestId("reorder-modal")).getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByTestId("reorder-modal")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /reorder waitlist/i }));
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("reorder-modal")).not.toBeInTheDocument());
  });

  it("is not offered to organizers", async () => {
    mockUser.role = "organizer";
    api.admin.eventRoster.mockResolvedValue(waitlist);
    renderPage();
    await screen.findByText("First");
    expect(screen.queryByRole("button", { name: /reorder waitlist/i })).not.toBeInTheDocument();
  });
});

describe("export, reopen and header buttons", () => {
  it("downloads the roster CSV after confirming", async () => {
    downloadBlob.mockResolvedValue();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /roster csv/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /roster csv/i }));
    await userEvent.click(screen.getByRole("button", { name: /download csv/i }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Roster CSV download started."));
    expect(downloadBlob).toHaveBeenCalledWith(
      "/admin/events/evt-1/export_csv", "event_evt-1_roster.csv", { auth: true },
    );
  });

  it("shows an export failure on the page", async () => {
    downloadBlob.mockRejectedValueOnce(new Error("Forbidden")).mockRejectedValueOnce({});
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /roster csv/i }));
    await userEvent.click(screen.getByRole("button", { name: /download csv/i }));
    expect(await screen.findByText("Forbidden")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /download csv/i }));
    expect(await screen.findByText("Export failed")).toBeInTheDocument();
  });

  it("reopens a completed event, and reports a failure", async () => {
    api.events.get.mockResolvedValue({ ...EVENT, completed_at: "2026-10-22T21:00:00Z" });
    reopenEvent.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("locked")).mockRejectedValueOnce({});
    renderPage();
    const btn = await screen.findByRole("button", { name: /reopen event/i });
    await userEvent.click(btn);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/reopened/i)));
    await userEvent.click(btn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("locked"));
    await userEvent.click(btn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Couldn't reopen the event"));
  });

  it.each([
    ["Event settings", "settings"],
    ["Check-in QR", "checkin-qr"],
    ["Signup QR", "signup-qr"],
    ["Message volunteers", "broadcast"],
    ["Duplicate…", "duplicate"],
    ["Add volunteer", "add-volunteer"],
  ])("%s opens and closes its modal", async (label, testId) => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: label }));
    expect(screen.getByTestId(testId)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `close ${testId}` }));
    expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
  });

  it("gives organizers the organizer broadcast scope and no Duplicate", async () => {
    mockUser.role = "organizer";
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Message volunteers" }));
    expect(screen.getByTestId("broadcast").dataset.scope).toBe("organizer");
    expect(screen.queryByRole("button", { name: "Duplicate…" })).not.toBeInTheDocument();
  });

  it("treats an archived quarter as read-only", async () => {
    api.public.getQuarters.mockResolvedValue([{ ...ACTIVE_QUARTER, archived_at: "2026-01-01" }]);
    renderPage();
    expect(await screen.findByText(/Read-only \(quarter ended\)/)).toBeInTheDocument();
  });
});
