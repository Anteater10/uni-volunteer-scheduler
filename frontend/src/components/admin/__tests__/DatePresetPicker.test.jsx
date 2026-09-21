import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import DatePresetPicker, { rangeForPreset } from "../DatePresetPicker";

describe("DatePresetPicker", () => {
  it("emits ISO {from,to} range when 7d preset is clicked", () => {
    const onChange = vi.fn();
    render(
      <DatePresetPicker value={{ preset: "24h" }} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /last 7d/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    const call = onChange.mock.calls[0][0];
    expect(call.preset).toBe("7d");
    expect(typeof call.from).toBe("string");
    expect(typeof call.to).toBe("string");
    // 7d window should be ~7 days apart
    const diff = new Date(call.to).getTime() - new Date(call.from).getTime();
    expect(diff).toBeGreaterThan(6 * 24 * 3600 * 1000);
    expect(diff).toBeLessThan(8 * 24 * 3600 * 1000);
  });

  it("reveals custom date inputs when preset=custom", () => {
    const onChange = vi.fn();
    render(
      <DatePresetPicker value={{ preset: "custom" }} onChange={onChange} />,
    );
    expect(screen.getByLabelText(/from/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/to/i)).toBeInTheDocument();
  });

  // Issue #24: "this quarter" derives from the admin-entered quarter rows.
  const QUARTERS = [
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
  ];

  it("rangeForPreset('quarter') uses the entered quarter covering the date", () => {
    const r = rangeForPreset("quarter", new Date(Date.UTC(2026, 3, 15)), QUARTERS);
    expect(r.from.slice(0, 10)).toBe("2026-03-30");
    // end_date is inclusive, so the exclusive filter bound is the next day
    expect(r.to.slice(0, 10)).toBe("2026-06-15");
  });

  it("rangeForPreset('quarter') is empty when no quarters are entered", () => {
    const r = rangeForPreset("quarter", new Date(Date.UTC(2026, 3, 15)), []);
    expect(r).toEqual({ from: null, to: null });
  });

  // L4 #41/C: the Exports screen offers these two, and neither existed here.
  // Their buttons showed their raw keys and their range fell through to
  // {null, null}, which the export reads as "no filter" — so a button that
  // looked like a date filter downloaded every record ever, PII included.
  const TWO_QUARTERS = [
    {
      id: "winter-26",
      season: "winter",
      year: 2026,
      start_date: "2026-01-05",
      end_date: "2026-03-20",
      display_name: "Winter 2026",
      archived_at: null,
    },
    ...QUARTERS,
  ];

  it("rangeForPreset('last-quarter') is the quarter before this one", () => {
    const r = rangeForPreset(
      "last-quarter",
      new Date(Date.UTC(2026, 3, 15)),
      TWO_QUARTERS,
    );
    expect(r.from.slice(0, 10)).toBe("2026-01-05");
    expect(r.to.slice(0, 10)).toBe("2026-03-21");
  });

  it("rangeForPreset('last-12-months') spans a year back from now", () => {
    const now = new Date(Date.UTC(2026, 3, 15));
    const r = rangeForPreset("last-12-months", now, TWO_QUARTERS);
    const days = (new Date(r.to) - new Date(r.from)) / (24 * 3600 * 1000);
    expect(Math.round(days)).toBe(365);
    expect(r.to).toBe(now.toISOString());
  });

  it("labels both presets in words, not their keys", () => {
    render(
      <DatePresetPicker
        value={{ preset: "quarter" }}
        onChange={() => {}}
        presets={["quarter", "last-quarter", "last-12-months", "custom"]}
        quarters={TWO_QUARTERS}
      />,
    );
    expect(screen.getByRole("button", { name: "Last quarter" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Last 12 months" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "last-quarter" })).not.toBeInTheDocument();
  });

  it("hides 'Last quarter' when no quarter has ended yet", () => {
    // Rows exist, but none has ended — resolving one would give an empty
    // range, and an empty range means an all-time export. The component reads
    // the real clock, so this row has to be dated ahead of it.
    const NOT_YET_ENDED = [
      {
        id: "future",
        season: "fall",
        year: 2099,
        start_date: "2099-09-01",
        end_date: "2099-12-01",
        display_name: "Fall 2099",
        archived_at: null,
      },
    ];
    render(
      <DatePresetPicker
        value={{ preset: "quarter" }}
        onChange={() => {}}
        presets={["quarter", "last-quarter", "custom"]}
        quarters={NOT_YET_ENDED}
      />,
    );
    expect(screen.getByRole("button", { name: "This quarter" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Last quarter" }),
    ).not.toBeInTheDocument();
  });

  it("hides the quarter preset when no quarters are available", () => {
    render(<DatePresetPicker value={{ preset: "7d" }} onChange={() => {}} quarters={[]} />);
    expect(screen.queryByRole("button", { name: /this quarter/i })).toBeNull();
  });

  it("shows the quarter preset and emits its range when quarters exist", () => {
    const onChange = vi.fn();
    render(
      <DatePresetPicker value={{ preset: "7d" }} onChange={onChange} quarters={QUARTERS} />,
    );
    // Pretend "today" is inside spring via the picker's now prop
    fireEvent.click(screen.getByRole("button", { name: /this quarter/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].preset).toBe("quarter");
  });
});
