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

  it("rangeForPreset('quarter') returns ISO start/end for current quarter", () => {
    const r = rangeForPreset("quarter", new Date(Date.UTC(2026, 3, 15)));
    expect(r.from.slice(0, 10)).toBe("2026-03-30");
    expect(r.to.slice(0, 10)).toBe("2026-06-15");
  });
});
