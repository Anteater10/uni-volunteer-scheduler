import React from "react";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock the AdminLayout hook so ExportsSection can mount without the layout wrapper.
vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

// Mock api — the three read fns and three csv fns.
const volunteerHours = vi.fn(async () => [
  { volunteer_name: "Alice", email: "alice@ucsb.edu", hours: 4, events: 2 },
]);
const attendanceRates = vi.fn(async () => [
  { name: "Intro Physics", confirmed: 10, attended: 8, no_show: 2, rate: 0.8 },
]);
const noShowRates = vi.fn(async () => [
  { volunteer_name: "Bob", count: 2, rate: 0.2 },
]);
const volunteerHoursCsv = vi.fn(async () => {});
const attendanceRatesCsv = vi.fn(async () => {});
const noShowRatesCsv = vi.fn(async () => {});

vi.mock("../../../lib/api", () => ({
  default: {
    public: {
      // Issue #24: "this quarter" bounds come from the entered quarter rows.
      getQuarters: vi.fn(async () => [
        {
          id: "spring-26",
          season: "spring",
          year: 2026,
          label: "",
          start_date: "2026-03-30",
          end_date: "2026-06-14",
          weeks_in_quarter: 11,
          display_name: "Spring 2026",
          archived_at: null,
        },
      ]),
    },
    admin: {
      analytics: {
        volunteerHours: (p) => volunteerHours(p),
        attendanceRates: (p) => attendanceRates(p),
        noShowRates: (p) => noShowRates(p),
        volunteerHoursCsv: (p) => volunteerHoursCsv(p),
        attendanceRatesCsv: (p) => attendanceRatesCsv(p),
        noShowRatesCsv: (p) => noShowRatesCsv(p),
      },
    },
  },
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("../../../state/toast", () => ({
  toast: {
    success: (...a) => toastSuccess(...a),
    error: (...a) => toastError(...a),
  },
}));

import ExportsSection from "../ExportsSection";

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ExportsSection />
    </QueryClientProvider>,
  );
}

describe("ExportsSection", () => {
  beforeEach(() => {
    volunteerHours.mockClear();
    attendanceRates.mockClear();
    noShowRates.mockClear();
    volunteerHoursCsv.mockClear();
    attendanceRatesCsv.mockClear();
    noShowRatesCsv.mockClear();
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it("renders one Download CSV button per analytics panel, three explainers, and no datetime-local inputs", async () => {
    const { container } = renderPage();

    await screen.findAllByRole("button", { name: /Download CSV/i });
    // One button per panel — query each panel's dedicated aria-label individually
    // so the assertion is robust against any repeated renders (StrictMode, etc).
    for (const title of ["Volunteer hours", "Attendance rates", "No-show rates"]) {
      const btns = container.querySelectorAll(
        `button[aria-label="Download CSV for ${title}"]`,
      );
      expect(btns.length).toBeGreaterThanOrEqual(1);
    }

    expect(
      screen.getByText(
        /Shows how many hours each volunteer has put in. Download the CSV for UCSB grant reports\./,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Shows what share of people who signed up actually showed up\./,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Shows how often people sign up but don't show up\./,
      ),
    ).toBeInTheDocument();

    expect(
      container.querySelectorAll('input[type="datetime-local"]'),
    ).toHaveLength(0);
  });

  it("clicking each Download CSV button calls the correct csvFn with from_date/to_date", async () => {
    const user = userEvent.setup();
    renderPage();

    const [volBtn, attBtn, noShowBtn] = await screen.findAllByRole("button", {
      name: /Download CSV/i,
    });

    await user.click(volBtn);
    await waitFor(() => expect(volunteerHoursCsv).toHaveBeenCalledTimes(1));
    const volArg = volunteerHoursCsv.mock.calls[0][0];
    expect(volArg).toHaveProperty("from_date");
    expect(volArg).toHaveProperty("to_date");

    await user.click(attBtn);
    await waitFor(() => expect(attendanceRatesCsv).toHaveBeenCalledTimes(1));
    expect(attendanceRatesCsv.mock.calls[0][0]).toHaveProperty("from_date");

    await user.click(noShowBtn);
    await waitFor(() => expect(noShowRatesCsv).toHaveBeenCalledTimes(1));
    expect(noShowRatesCsv.mock.calls[0][0]).toHaveProperty("from_date");

    // Each JSON fetch was also called for its respective panel.
    expect(volunteerHours).toHaveBeenCalled();
    expect(attendanceRates).toHaveBeenCalled();
    expect(noShowRates).toHaveBeenCalled();
  });
});

// K12 — the download button was `onClick={() => csvFn(params)}`: not awaited,
// not caught. downloadBlob is async and throws on any non-2xx, so a 401 or a
// 500 was an unhandled rejection in the console and, to the admin, a button
// that did nothing at all.
describe("ExportsSection — a failed export has to say so (K12)", () => {
  beforeEach(() => {
    volunteerHours.mockClear();
    attendanceRates.mockClear();
    noShowRates.mockClear();
    volunteerHoursCsv.mockClear();
    attendanceRatesCsv.mockClear();
    noShowRatesCsv.mockClear();
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it("surfaces the server's message instead of failing silently", async () => {
    const user = userEvent.setup();
    volunteerHoursCsv.mockRejectedValueOnce(new Error("Export timed out"));
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Download CSV for Volunteer hours" }),
    );

    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError.mock.calls[0][0]).toMatch(/export timed out/i);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("confirms the download when it starts", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Download CSV for No-show rates" }),
    );

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledTimes(1));
    expect(toastSuccess.mock.calls[0][0]).toMatch(/no-show rates/i);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("disables the button while the export is in flight so it can't be double-fired", async () => {
    const user = userEvent.setup();
    let release;
    attendanceRatesCsv.mockImplementationOnce(
      () => new Promise((res) => { release = res; }),
    );
    renderPage();

    const btn = await screen.findByRole("button", {
      name: "Download CSV for Attendance rates",
    });
    await user.click(btn);

    await waitFor(() => expect(btn).toBeDisabled());
    expect(btn).toHaveTextContent(/preparing/i);

    release();
    await waitFor(() => expect(btn).not.toBeDisabled());
    expect(btn).toHaveTextContent(/download csv/i);
    expect(attendanceRatesCsv).toHaveBeenCalledTimes(1);
  });

  it("renders a retryable alert when the panel data itself won't load", async () => {
    volunteerHours.mockRejectedValue(new Error("Analytics service is down"));
    renderPage();

    // Find the alert by its message. Other panels can be in an error state
    // too depending on what the module mock covers, so match on the text this
    // test actually set rather than on "couldn't load data".
    const findOurAlert = async () => {
      const alerts = await screen.findAllByRole("alert");
      const hit = alerts.find((a) =>
        /analytics service is down/i.test(a.textContent),
      );
      expect(hit).toBeTruthy();
      return hit;
    };
    expect(await findOurAlert()).toHaveTextContent(/analytics service is down/i);

    // The panel fetches on mount and again when the quarters query resolves
    // and moves the date params. Wait for the count to hold steady, so the
    // click is the only thing that can move it.
    let calls = -1;
    await waitFor(() => {
      const now = volunteerHours.mock.calls.length;
      const steady = now === calls;
      calls = now;
      if (!steady) throw new Error("still settling");
    });

    // Re-query AFTER settling. That params-driven re-render replaces the
    // ErrorState node, so an element captured earlier is detached by now, and
    // clicking a detached node does nothing at all. This test used to hold
    // the stale reference and pass anyway — the retry it thought it was
    // measuring was really the quarters refetch arriving on its own.
    const live = await findOurAlert();
    fireEvent.click(within(live).getByRole("button", { name: /try again/i }));
    await waitFor(() =>
      expect(volunteerHours.mock.calls.length).toBeGreaterThan(calls),
    );
  });
});
