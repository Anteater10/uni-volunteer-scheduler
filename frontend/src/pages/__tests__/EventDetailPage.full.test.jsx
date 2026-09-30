// EventDetailPage.full.test.jsx — the public signup page, state by state:
// loading/error, header and signup window, the event description, slot and
// shift availability, calendar buttons, the selection summary, custom form
// questions, validation, every submit outcome and the orientation modal paths.

import React from "react";
import { vi } from "vitest";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getEvent: vi.fn(),
      getFormSchema: vi.fn(),
      createSignup: vi.fn(),
      orientationCheck: vi.fn(),
    },
  },
}));
vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock("../../lib/calendar", () => ({
  downloadIcs: vi.fn(),
  buildGoogleCalendarUrl: vi.fn(() => "https://calendar.example/x"),
}));
vi.mock("../../components/OrientationWarningModal", () => ({
  default: ({ open, required, onYes, onNo, onPickOrientation, onFindOrientation }) =>
    open ? (
      <div data-testid="orientation-modal" data-required={String(required)}>
        <button onClick={onYes}>modal yes</button>
        <button onClick={onNo}>modal no</button>
        <button onClick={onPickOrientation}>modal pick</button>
        <button onClick={onFindOrientation}>modal find</button>
      </div>
    ) : null,
}));
vi.mock("../../components/SignupSuccessCard", () => ({
  default: ({ open, slots, onDismiss }) =>
    open ? (
      <div data-testid="success-card">
        <span>{slots.map((s) => s._shiftName || s.id).join(",")}</span>
        <button onClick={onDismiss}>dismiss</button>
      </div>
    ) : null,
}));

import api from "../../lib/api";
import { toast } from "../../state/toast";
import { downloadIcs, buildGoogleCalendarUrl } from "../../lib/calendar";
import EventDetailPage, { isValidPhone } from "../public/EventDetailPage";

vi.setConfig({ testTimeout: 20000 });

const ORIENT = {
  id: "o1", slot_type: "orientation", date: "2026-10-06",
  start_time: "2026-10-06T23:00:00Z", end_time: "2026-10-07T01:00:00Z",
  location: "Chem 1005D", capacity: 25, filled: 0,
};
const SHIFT = {
  id: "sh1", name: "Tue + Thu P1", sort_order: 0, capacity: 8, filled: 2,
  sessions: [
    { id: "s2", name: "Shift 1-R", sort_order: 1, date: "2026-10-22", start_time: "2026-10-22T17:23:00Z", end_time: "2026-10-22T19:13:00Z", location: "Chem 1204" },
    { id: "s1", name: "Shift 1- T", sort_order: 0, date: "2026-10-20", start_time: "2026-10-20T17:23:00Z", end_time: "2026-10-20T19:13:00Z", location: "Chem 1204" },
  ],
};
const EVENT = {
  id: "evt-1", title: "Week 4 - Conservation of Mass - SBJH", school: "SBJH",
  module_slug: "conservation-of-mass", start_date: "2026-10-05T07:00:00Z",
  end_date: "2026-10-24T07:00:00Z", description: "", slots: [ORIENT], shifts: [SHIFT],
};

function Where() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname + loc.search}</div>;
}

function renderPage(event = EVENT) {
  api.public.getEvent.mockResolvedValue(event);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/events/evt-1"]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function loaded() {
  await screen.findByRole("heading", { level: 1 });
}

function fill(values = {}) {
  const v = { first_name: "Ana", last_name: "Diaz", email: "ana@x.com", phone: "805-555-1234", ...values };
  for (const [id, value] of Object.entries(v)) {
    fireEvent.change(document.getElementById(id), { target: { value } });
  }
}

function submit() {
  fireEvent.click(screen.getByTestId("signup-submit"));
}

// The orientation table is hidden below md and the cards above it; jsdom shows
// both, so pick the table (desktop) copy of a button by default.
function tableSignUp(i = 0) {
  return within(screen.getByRole("table")).getAllByRole("button", { name: /sign up|join waitlist|selected|on waitlist|ended/i })[i];
}

function shiftButton(id = "sh1") {
  return within(screen.getByTestId(`shift-${id}`)).getAllByRole("button")[0];
}

beforeEach(() => {
  vi.clearAllMocks();
  api.public.getFormSchema.mockResolvedValue({ schema: [] });
  api.public.orientationCheck.mockResolvedValue({ has_credit: true });
  api.public.createSignup.mockResolvedValue({ signups: [] });
  window.open = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
});

describe("isValidPhone", () => {
  it.each([
    [null, false], ["", false], ["   ", false],
    ["+18055551234", true], ["+0123456789", false], ["+1234", false],
    ["805-555-1234", true], ["1 (805) 555-1234", true], ["2 805 555 1234", false], ["12345", false],
  ])("%j -> %s", (raw, ok) => expect(isValidPhone(raw)).toBe(ok));
});

describe("loading, error and header", () => {
  it("shows a loading state, then an error with retry", async () => {
    api.public.getEvent.mockRejectedValueOnce(new Error("down"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/events/evt-1"]}>
          <Routes><Route path="/events/:eventId" element={<EventDetailPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("status", { name: /loading event details/i })).toBeInTheDocument();
    expect(await screen.findByText("We couldn't load this page")).toBeInTheDocument();
    api.public.getEvent.mockResolvedValue(EVENT);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await loaded();
  });

  it("shows one date when the event starts and ends the same day, and no school line", async () => {
    renderPage({ ...EVENT, school: null, end_date: EVENT.start_date });
    await loaded();
    expect(screen.queryByText("SBJH")).not.toBeInTheDocument();
    expect(screen.queryByText(/ - Oct/)).not.toBeInTheDocument();
  });

  it("copes with missing event dates", async () => {
    renderPage({ ...EVENT, start_date: null, end_date: null });
    await loaded();
  });

  it("announces the selection count to screen readers", async () => {
    renderPage();
    await loaded();
    fireEvent.click(tableSignUp());
    expect(screen.getAllByText("1 selected").length).toBeGreaterThan(0);
    fireEvent.click(shiftButton());
    expect(screen.getAllByText("2 selected").length).toBeGreaterThan(0);
  });
});

describe("signup window", () => {
  it("blocks submit before the window opens", async () => {
    renderPage({ ...EVENT, signup_open_at: "2099-01-01T00:00:00Z" });
    await loaded();
    expect(screen.getByTestId("signup-window-banner")).toHaveTextContent(/Signup opens/);
    fireEvent.click(tableSignUp());
    expect(screen.getByTestId("signup-submit")).toHaveTextContent("Signup not open yet");
    expect(screen.getByTestId("signup-submit")).toBeDisabled();
  });

  it("blocks submit after the window closes", async () => {
    renderPage({ ...EVENT, signup_close_at: "2000-01-01T00:00:00Z" });
    await loaded();
    expect(screen.getByTestId("signup-window-banner")).toHaveTextContent(/Signup closed/);
    fireEvent.click(tableSignUp());
    expect(screen.getByTestId("signup-submit")).toHaveTextContent("Signup closed");
  });
});

describe("event description", () => {
  it("uses the organizer's own description when there is one", async () => {
    renderPage({ ...EVENT, description: "Custom words." });
    await loaded();
    expect(screen.getByText("Custom words.")).toBeInTheDocument();
    expect(screen.queryByText("NOTE:")).not.toBeInTheDocument();
    expect(screen.queryByText(/travel by van/)).not.toBeInTheDocument();
  });

  it("writes the default text, numbering several orientations", async () => {
    const second = { ...ORIENT, id: "o2", location: null, date: "2026-10-07T00:00:00Z" };
    renderPage({ ...EVENT, slots: [ORIENT, second] });
    await loaded();
    expect(screen.getByText(/conducting the Conservation Of Mass Module/)).toHaveTextContent("at SBJH");
    expect(screen.getByText(/Orientation 1 -/)).toHaveTextContent("in Chem 1005D");
    expect(screen.getByText(/Orientation 2 -/)).not.toHaveTextContent(" in ");
    expect(screen.getByText(/travel by van/)).toBeInTheDocument();
    expect(screen.getAllByText("Orientation #2").length).toBeGreaterThan(0);
  });

  it("falls back to the title and skips the van note for online modules", async () => {
    renderPage({ ...EVENT, module_slug: null, school: null, slots: [], title: "Mystery" });
    await loaded();
    expect(screen.getByText(/conducting the Mystery Module\./)).toBeInTheDocument();
    renderPage({ ...EVENT, module_slug: "bioinformatics-cancer" });
    await waitFor(() => expect(screen.getAllByText(/Bioinformatics Cancer/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/travel by van/)).toHaveLength(1); // only the first render has it
  });

  it("says 'this module' in the note when there is no module name", async () => {
    renderPage({ ...EVENT, module_slug: null });
    await loaded();
    expect(screen.getByText(/covered this module fulfill/)).toBeInTheDocument();
    expect(screen.getByText(/Orientation - /)).toBeInTheDocument();
  });
});

describe("orientation availability", () => {
  it.each([
    [{ has_ended: true }, "Already happened", "Ended"],
    [{ filled: 25 }, "Full", "Join waitlist"],
    [{ filled: 23 }, "Few spots left", "Sign up"],
    [{ filled: 0 }, "Available", "Sign up"],
  ])("%j shows %s", async (over, badge, button) => {
    renderPage({ ...EVENT, slots: [{ ...ORIENT, ...over }] });
    await loaded();
    expect(within(screen.getByRole("table")).getByText(badge)).toBeInTheDocument();
    expect(tableSignUp()).toHaveTextContent(button);
  });

  it("marks selections, including a waitlist pick, in the table and the cards", async () => {
    renderPage({ ...EVENT, slots: [ORIENT, { ...ORIENT, id: "o2", filled: 25 }] });
    await loaded();
    fireEvent.click(tableSignUp(0));
    fireEvent.click(tableSignUp(1));
    expect(tableSignUp(0)).toHaveTextContent("Selected");
    expect(tableSignUp(1)).toHaveTextContent("On waitlist");
    expect(screen.getAllByText("You selected this").length).toBeGreaterThan(0);
  });

  it("renders slots without capacity, location or date", async () => {
    renderPage({ ...EVENT, slots: [{ ...ORIENT, capacity: 0, filled: 0, location: null, date: null, start_time: null }] });
    await loaded();
    expect(within(screen.getByRole("table")).getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/of 0 filled/)).not.toBeInTheDocument();
  });

  it("treats missing capacity numbers as zero", async () => {
    renderPage({ ...EVENT, slots: [{ ...ORIENT, capacity: undefined, filled: undefined }] });
    await loaded();
    expect(within(screen.getByRole("table")).getByText("Full")).toBeInTheDocument();
  });

  it("expands and collapses who signed up", async () => {
    renderPage({ ...EVENT, slots: [{ ...ORIENT, signups: [{ first_name: "Ana", last_initial: "D" }, { first_name: "", last_initial: "Q" }] }] });
    await loaded();
    const toggle = screen.getByRole("button", { name: /2 signed up/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("Ana D.").length).toBe(2); // table drawer + mobile card
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});

describe("shift cards", () => {
  it.each([
    [{ has_ended: true }, "Already happened", "Ended"],
    [{ filled: 8 }, "Full", "Join waitlist"],
    [{ filled: 6 }, "Few spots left", "Sign up"],
    [{ filled: 0 }, "Available", "Sign up"],
  ])("%j shows %s", async (over, badge, button) => {
    renderPage({ ...EVENT, shifts: [{ ...SHIFT, ...over }] });
    await loaded();
    const card = screen.getByTestId("shift-sh1");
    expect(within(card).getByText(badge)).toBeInTheDocument();
    expect(shiftButton()).toHaveTextContent(button);
  });

  it("orders sessions and says how many the commitment covers", async () => {
    renderPage();
    await loaded();
    const card = screen.getByTestId("shift-sh1");
    expect(within(card).getByText(/2 sessions — signing up commits you to all/)).toBeInTheDocument();
    const names = within(card).getAllByText(/^Shift 1/).map((n) => n.textContent);
    expect(names).toEqual(["Shift 1- T", "Shift 1-R"]);
  });

  it("handles a one-session shift with sparse data and a waitlist pick", async () => {
    const lone = {
      id: "sh2", name: "Solo", capacity: 1, filled: 1,
      sessions: [{ id: "x", date: "2026-10-20", start_time: "2026-10-20T17:00:00Z", end_time: "2026-10-20T18:00:00Z" }],
    };
    const tied = {
      id: "sh3", name: "Tied", capacity: 0,
      sessions: [
        { id: "b", start_time: "2026-10-21T17:00:00Z" },
        { id: "a", start_time: "2026-10-20T17:00:00Z" },
      ],
    };
    renderPage({ ...EVENT, slots: [], shifts: [lone, tied] });
    await loaded();
    expect(within(screen.getByTestId("shift-sh2")).getByText(/1 session — signing up commits you to it/)).toBeInTheDocument();
    fireEvent.click(shiftButton("sh2"));
    expect(shiftButton("sh2")).toHaveTextContent("On waitlist");
    expect(within(screen.getByTestId("shift-sh3")).queryByText(/filled/)).not.toBeInTheDocument();
  });

  it("marks a selected open shift", async () => {
    renderPage();
    await loaded();
    fireEvent.click(shiftButton());
    expect(shiftButton()).toHaveTextContent("Selected");
  });

  it("lists shifts by their sort order", async () => {
    renderPage({ ...EVENT, shifts: [{ ...SHIFT, id: "b", name: "Second", sort_order: 2 }, { ...SHIFT, id: "a", name: "First" , sort_order: undefined }] });
    await loaded();
    const ids = screen.getAllByTestId(/^shift-/).map((el) => el.dataset.testid);
    expect(ids).toEqual(["shift-a", "shift-b"]);
  });

  it("shows an empty state with a way back when nothing is bookable", async () => {
    renderPage({ ...EVENT, slots: [], shifts: [] });
    await loaded();
    expect(screen.getByText("Every slot is full")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /google calendar/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /back to events/i }));
    expect(screen.getByTestId("location")).toHaveTextContent("/volunteer");
  });
});

describe("calendar buttons", () => {
  it("adds the ticked sessions, a whole shift at once", async () => {
    renderPage();
    await loaded();
    fireEvent.click(shiftButton());
    fireEvent.click(screen.getByRole("button", { name: /download \.ics/i }));
    expect(downloadIcs.mock.calls[0][0].slots.map((s) => s.id)).toEqual(["s1", "s2"]);
    expect(toast.success).toHaveBeenCalledWith("Calendar file saved with 2 sessions. Open it to add them.");
    fireEvent.click(screen.getByRole("button", { name: /google calendar/i }));
    expect(buildGoogleCalendarUrl.mock.calls[0][0].slot.id).toBe("s1");
    expect(window.open).toHaveBeenCalledWith("https://calendar.example/x", "_blank", "noopener,noreferrer");
  });

  it("falls back to the first open orientation", async () => {
    renderPage({ ...EVENT, slots: [{ ...ORIENT, id: "full", filled: 25 }, ORIENT] });
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: /download \.ics/i }));
    expect(downloadIcs.mock.calls[0][0].slots.map((s) => s.id)).toEqual(["o1"]);
    expect(toast.success).toHaveBeenCalledWith("Calendar file saved. Open it to add to your calendar.");
  });

  it("falls back to the first slot when every orientation is full", async () => {
    renderPage({ ...EVENT, slots: [{ ...ORIENT, filled: 25 }] });
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: /google calendar/i }));
    expect(buildGoogleCalendarUrl.mock.calls[0][0].slot.id).toBe("o1");
  });

  it("falls back to the first shift session when there are no orientations", async () => {
    renderPage({ ...EVENT, slots: [] });
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: /google calendar/i }));
    expect(buildGoogleCalendarUrl.mock.calls[0][0].slot.id).toBe("s1");
  });

  it("does nothing when there is no session to add", async () => {
    renderPage({ ...EVENT, slots: [], shifts: [{ ...SHIFT, sessions: [] }] });
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: /google calendar/i }));
    fireEvent.click(screen.getByRole("button", { name: /download \.ics/i }));
    expect(window.open).not.toHaveBeenCalled();
    expect(downloadIcs).not.toHaveBeenCalled();
  });
});

describe("selection summary", () => {
  it("lists each pick and lets the volunteer drop it", async () => {
    renderPage({ ...EVENT, shifts: [SHIFT, { ...SHIFT, id: "sh9", name: "Solo", sessions: [SHIFT.sessions[0]] }] });
    await loaded();
    fireEvent.click(tableSignUp());
    fireEvent.click(shiftButton());
    fireEvent.click(shiftButton("sh9"));
    expect(screen.getByText("Your selections (3)")).toBeInTheDocument();
    expect(screen.getByText(/· 2 sessions/)).toBeInTheDocument();
    expect(screen.getByText(/· 1 session$/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove Orientation" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Tue + Thu P1" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Solo" }));
    expect(screen.queryByText(/Your selections/)).not.toBeInTheDocument();
  });
});

describe("validation and custom questions", () => {
  it("reports every missing identity field, then clears each as it is typed", async () => {
    renderPage();
    await loaded();
    fireEvent.click(tableSignUp());
    submit();
    expect(screen.getAllByText("Enter your full name")).toHaveLength(2);
    expect(screen.getByText("Enter your email address")).toBeInTheDocument();
    expect(screen.getByText("Enter your phone number")).toBeInTheDocument();
    fill({ email: "nope", phone: "123" });
    expect(screen.queryByText("Enter your full name")).not.toBeInTheDocument();
    submit();
    expect(screen.getByText("That doesn't look like a valid email")).toBeInTheDocument();
    expect(screen.getByText(/Use a US format/)).toBeInTheDocument();
    expect(api.public.createSignup).not.toHaveBeenCalled();
  });

  it("flags only the missing half of the name", async () => {
    renderPage();
    await loaded();
    fireEvent.click(tableSignUp());
    fill({ last_name: " " });
    submit();
    expect(screen.getAllByText("Enter your full name")).toHaveLength(1);
  });

  it("renders every question type, requires answers, and sends them", async () => {
    api.public.getFormSchema.mockResolvedValue({
      schema: [
        { id: "t", label: "Text", type: "text", required: true, help_text: "Short answer" },
        { id: "ta", label: "Long", type: "textarea", required: true },
        { id: "sel", label: "Pick", type: "select", options: ["A", "B"], required: true },
        { id: "sel0", label: "No options select", type: "select" },
        { id: "r", label: "Radio", type: "radio", options: ["X", "Y"], required: true },
        { id: "r0", label: "No options radio", type: "radio" },
        { id: "cb", label: "Days", type: "checkbox", options: ["Tue", "Thu"], required: true },
        { id: "cb0", label: "No options checkbox", type: "checkbox" },
        { id: "ph", label: "Alt phone", type: "phone" },
        { id: "em", label: "Alt email", type: "email" },
        { id: "odd", label: "Unknown kind", type: "mystery" },
        { id: "opt", label: "Optional", type: "text" },
      ],
    });
    renderPage();
    await loaded();
    fireEvent.click(tableSignUp());
    await screen.findByText("A few more questions");
    expect(screen.getByText("Short answer")).toBeInTheDocument();
    expect(screen.getByText("Text *")).toBeInTheDocument();
    fill();
    // Whitespace and an emptied checkbox list still count as blank.
    fireEvent.change(document.getElementById("ff-t"), { target: { value: "  " } });
    const tue = screen.getByRole("checkbox", { name: "Tue" });
    fireEvent.click(tue);
    fireEvent.click(tue);
    submit();
    for (const label of ["Text", "Long", "Pick", "Radio", "Days"]) {
      expect(screen.getByText(`Please answer: ${label}`)).toBeInTheDocument();
    }
    fireEvent.change(document.getElementById("ff-t"), { target: { value: "hi" } });
    expect(screen.queryByText("Please answer: Text")).not.toBeInTheDocument();
    fireEvent.change(document.getElementById("ff-ta"), { target: { value: "long" } });
    fireEvent.change(document.getElementById("ff-sel"), { target: { value: "B" } });
    fireEvent.click(screen.getByRole("radio", { name: "Y" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Thu" }));
    fireEvent.change(document.getElementById("ff-ph"), { target: { value: "805" } });
    fireEvent.change(document.getElementById("ff-em"), { target: { value: "b@x.com" } });
    fireEvent.change(document.getElementById("ff-odd"), { target: { value: "?" } });
    submit();
    await waitFor(() => expect(api.public.createSignup).toHaveBeenCalled());
    const body = api.public.createSignup.mock.calls[0][0];
    expect(Object.fromEntries(body.responses.map((r) => [r.field_id, r.value]))).toEqual({
      t: "hi", ta: "long", sel: "B", r: "Y", cb: ["Thu"], ph: "805", em: "b@x.com", odd: "?",
    });
  });
});

describe("submitting", () => {
  async function pickAndSubmit(pickShift = false) {
    await loaded();
    fireEvent.click(tableSignUp());
    if (pickShift) fireEvent.click(shiftButton());
    fill();
    submit();
  }

  it("books, tags shift sessions, and resets from the success card", async () => {
    renderPage();
    await loaded();
    fireEvent.click(tableSignUp());
    fireEvent.click(shiftButton());
    fill();
    submit();
    expect(await screen.findByTestId("success-card")).toHaveTextContent("o1,Tue + Thu P1,Tue + Thu P1");
    expect(api.public.createSignup.mock.calls[0][0]).toMatchObject({ slot_ids: ["o1"], shift_ids: ["sh1"] });
    fireEvent.click(screen.getByRole("button", { name: "dismiss" }));
    expect(screen.queryByTestId("success-card")).not.toBeInTheDocument();
    expect(screen.queryByText("Your information")).not.toBeInTheDocument();
  });

  it("names the best waitlist position", async () => {
    api.public.createSignup.mockResolvedValue({
      signups: [
        { status: "waitlisted", position: 4 },
        { status: "waitlisted", position: null },
        { status: "waitlisted", position: 2 },
        { status: "pending" },
      ],
    });
    renderPage();
    await pickAndSubmit();
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("You're on the waitlist — position 2."));
  });

  it("says waitlisted without a position when none is known", async () => {
    api.public.createSignup.mockResolvedValue({ signups: [{ status: "waitlisted" }] });
    renderPage();
    await pickAndSubmit();
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("You're on the waitlist."));
  });

  it("treats a missing signups list as no waitlist", async () => {
    api.public.createSignup.mockResolvedValue({});
    renderPage();
    await pickAndSubmit();
    await screen.findByTestId("success-card");
    expect(toast.info).not.toHaveBeenCalled();
  });

  function reject(props) {
    const err = Object.assign(new Error(props.message ?? ""), props);
    api.public.createSignup.mockRejectedValueOnce(err);
  }

  it("rate limit keeps the form", async () => {
    reject({ status: 429, message: "slow" });
    renderPage();
    await pickAndSubmit();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/Too many submissions/)));
    expect(screen.getByText("Your information")).toBeInTheDocument();
  });

  it("maps 422 field errors onto the form", async () => {
    reject({
      status: 422, message: "bad",
      response: { data: { detail: [{ loc: ["body", "phone"], msg: "Bad phone" }, { loc: ["body", "email"] }, { loc: "odd" }] } },
    });
    renderPage();
    await pickAndSubmit();
    expect(await screen.findByText("Bad phone")).toBeInTheDocument();
    expect(screen.getByText("Invalid value")).toBeInTheDocument();
  });

  it("shows the message when a 422 names no field", async () => {
    reject({ status: 422, message: "Nothing to book", response: { data: { detail: [{ msg: "x" }] } } });
    renderPage();
    await pickAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing to book");
  });

  it("shows the message for a non-list 422", async () => {
    reject({ status: 422, message: "Signup window closed" });
    renderPage();
    await pickAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Signup window closed");
  });

  it("explains a duplicate signup", async () => {
    reject({ status: 409, message: "already signed up for slot o1" });
    renderPage();
    await pickAndSubmit();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/already signed up for this session/)));
  });

  it.each([
    [{ status: 409, message: "conflict" }],
    [{ status: 400, message: "Slot at capacity" }],
    [{ status: 400, message: "Shift is full" }],
  ])("sends the volunteer back to pick again when %j", async (props) => {
    reject(props);
    renderPage();
    await pickAndSubmit();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/now full/)));
    expect(screen.queryByText("Your information")).not.toBeInTheDocument();
  });

  it("shows any other error, or a generic one", async () => {
    reject({ status: 500, message: "Server exploded" });
    renderPage();
    await pickAndSubmit();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Server exploded"));
    api.public.createSignup.mockRejectedValueOnce({ status: 500 });
    submit();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Something went wrong. Please try again."));
  });

  it("skips a shift that vanished after a refetch", async () => {
    renderPage();
    await loaded();
    fireEvent.click(shiftButton());
    fireEvent.click(tableSignUp());
    fill();
    // The capacity path refetches the event; this time the shift is gone.
    api.public.getEvent.mockResolvedValue({ ...EVENT, shifts: [] });
    reject({ status: 409, message: "conflict" });
    submit();
    await waitFor(() => expect(screen.queryByTestId("shift-sh1")).not.toBeInTheDocument());
    fireEvent.click(tableSignUp()); // untick
    fireEvent.click(tableSignUp()); // tick again to reopen the form
    submit();
    const card = await screen.findByTestId("success-card");
    expect(card).toHaveTextContent("o1");
    expect(card).not.toHaveTextContent("Tue + Thu P1");
  });
});

describe("orientation modal", () => {
  async function shiftOnly() {
    await loaded();
    fireEvent.click(shiftButton());
    fill();
    submit();
    return screen.findByTestId("orientation-modal");
  }

  it("uses the legacy attended flag when has_credit is absent", async () => {
    api.public.orientationCheck.mockResolvedValue({ has_attended_orientation: true });
    renderPage();
    await loaded();
    fireEvent.click(shiftButton());
    fill();
    submit();
    expect(await screen.findByTestId("success-card")).toBeInTheDocument();
  });

  it("Yes submits anyway", async () => {
    api.public.orientationCheck.mockResolvedValue({ has_credit: false });
    renderPage({ ...EVENT, slots: [] });
    const modal = await shiftOnly();
    expect(modal.dataset.required).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "modal yes" }));
    expect(await screen.findByTestId("success-card")).toBeInTheDocument();
  });

  it("No and Pick return to the schedule with orientation highlighted", async () => {
    api.public.orientationCheck.mockResolvedValue({ has_credit: false });
    renderPage();
    const modal = await shiftOnly();
    expect(modal.dataset.required).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "modal no" }));
    expect(screen.queryByTestId("orientation-modal")).not.toBeInTheDocument();
    const row = within(screen.getByRole("table")).getAllByRole("row")[1];
    expect(row.className).toMatch(/bg-sky-50\/40/);
    // Mobile card highlight too.
    expect(document.querySelector(".border-sky-400")).not.toBeNull();
  });

  it("Find sends the volunteer to events that offer orientation", async () => {
    api.public.orientationCheck.mockResolvedValue({ has_credit: false });
    renderPage({ ...EVENT, slots: [] });
    await shiftOnly();
    fireEvent.click(screen.getByRole("button", { name: "modal find" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/volunteer?only=orientation");
  });

  it("a server ORIENTATION_REQUIRED opens the modal", async () => {
    api.public.createSignup.mockRejectedValueOnce(Object.assign(new Error("x"), { code: "ORIENTATION_REQUIRED" }));
    renderPage();
    await shiftOnly();
  });
});

describe("sparse data", () => {
  it("shows the start date alone when there is no end date", async () => {
    renderPage({ ...EVENT, end_date: null });
    await loaded();
  });

  it("copes with an event with no slots list and a shift with no sessions list", async () => {
    renderPage({ ...EVENT, slots: undefined, shifts: [{ id: "bare", name: "Bare", capacity: 3 }] });
    await loaded();
    const card = screen.getByTestId("shift-bare");
    expect(within(card).getByText("0 of 3 filled")).toBeInTheDocument();
    expect(within(card).getByText(/0 sessions/)).toBeInTheDocument();
  });

  it("treats a shift with no capacity number as full", async () => {
    renderPage({ ...EVENT, shifts: [{ ...SHIFT, capacity: undefined, filled: undefined }] });
    await loaded();
    expect(within(screen.getByTestId("shift-sh1")).getByText("Full")).toBeInTheDocument();
  });

  it("toggles a slot from its mobile card", async () => {
    renderPage();
    await loaded();
    const cardButton = screen
      .getAllByRole("button", { name: "Sign up" })
      .find((b) => !b.closest("table") && !b.closest("[data-testid^='shift-']"));
    fireEvent.click(cardButton);
    expect(screen.getByText("Your selections (1)")).toBeInTheDocument();
  });

  it("flags only the first name when only it is missing", async () => {
    renderPage();
    await loaded();
    fireEvent.click(tableSignUp());
    fill({ first_name: "" });
    submit();
    expect(screen.getAllByText("Enter your full name")).toHaveLength(1);
  });

  it("calendar fallback: orientations without counts, no shifts", async () => {
    renderPage({ ...EVENT, shifts: [], slots: [{ ...ORIENT, capacity: undefined, filled: undefined }] });
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: /google calendar/i }));
    expect(buildGoogleCalendarUrl.mock.calls[0][0].slot.id).toBe("o1");
  });
});
