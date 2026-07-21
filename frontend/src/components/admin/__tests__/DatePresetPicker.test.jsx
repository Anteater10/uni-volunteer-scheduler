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
