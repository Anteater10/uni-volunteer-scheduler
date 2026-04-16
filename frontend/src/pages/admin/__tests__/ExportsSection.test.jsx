import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
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
  });

  it("renders three Download CSV buttons, three explainers, and no datetime-local inputs", async () => {
    const { container } = renderPage();

    const buttons = await screen.findAllByRole("button", {
      name: /Download CSV/i,
    });
    expect(buttons).toHaveLength(3);

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
