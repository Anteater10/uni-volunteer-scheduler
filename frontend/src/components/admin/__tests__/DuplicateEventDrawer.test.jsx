import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DuplicateEventDrawer from "../DuplicateEventDrawer";

const SOURCE = {
  id: "src-1",
  title: "CRISPR Lab",
  module_slug: "crispr",
  quarter: "spring",
  year: 2026,
  week_number: 4,
};

function renderDrawer(props = {}) {
  const defaults = {
    open: true,
    onClose: () => {},
    sourceEvent: SOURCE,
    existingEvents: [],
    onSubmit: vi.fn(),
    submitting: false,
  };
  return render(<DuplicateEventDrawer {...defaults} {...props} />);
}

describe("DuplicateEventDrawer", () => {
  it("renders 11 week chips and highlights conflict weeks", () => {
    renderDrawer({
      existingEvents: [
        { id: "x", module_slug: "crispr", week_number: 7, year: 2026 },
      ],
    });
    // 11 week chips + source week is implicit conflict (week 4)
    const chips = screen.getAllByTestId(/week-chip-/);
    expect(chips.length).toBe(11);

    const week7 = screen.getByTestId("week-chip-7");
    expect(week7.getAttribute("data-conflict")).toBe("true");

    const week4 = screen.getByTestId("week-chip-4");
    expect(week4.getAttribute("data-conflict")).toBe("true"); // source's own week

    const week5 = screen.getByTestId("week-chip-5");
    expect(week5.getAttribute("data-conflict")).toBe("false");
  });

  it("updates preview as weeks are toggled", () => {
    renderDrawer();
    fireEvent.click(screen.getByTestId("week-chip-5"));
    fireEvent.click(screen.getByTestId("week-chip-6"));
    fireEvent.click(screen.getByTestId("week-chip-7"));
    const preview = screen.getByTestId("preview");
    expect(preview.textContent).toMatch(/Creating 3 events/);
    expect(preview.textContent).toMatch(/weeks 5, 6, 7/);
  });

  it("flags skipped conflicts in the preview copy", () => {
    renderDrawer({
      existingEvents: [
        { id: "x", module_slug: "crispr", week_number: 7, year: 2026 },
      ],
    });
    fireEvent.click(screen.getByTestId("week-chip-5"));
    fireEvent.click(screen.getByTestId("week-chip-7"));
    const preview = screen.getByTestId("preview");
    // 1 creating (week 5), 1 conflict (week 7 is already taken).
    expect(preview.textContent).toMatch(/Creating 1 event/);
    expect(preview.textContent).toMatch(/1 conflict/);
    expect(preview.textContent).toMatch(/will be skipped/);
  });

  it("submits with the correct payload and respects skip-conflicts", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ created: [], skipped_conflicts: [] });
    renderDrawer({ onSubmit });

    fireEvent.click(screen.getByTestId("week-chip-5"));
    fireEvent.click(screen.getByTestId("week-chip-6"));
    fireEvent.click(screen.getByTestId("submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      target_weeks: [5, 6],
      target_year: 2026,
      target_quarter: "spring",
      skip_conflicts: true,
    });
  });

  it("disables submit until a week is selected", () => {
    renderDrawer();
    expect(screen.getByTestId("submit")).toBeDisabled();
    fireEvent.click(screen.getByTestId("week-chip-5"));
    expect(screen.getByTestId("submit")).not.toBeDisabled();
  });

  it("changes copy when skip-conflicts is disabled and conflicts are selected", () => {
    renderDrawer({
      existingEvents: [
        { id: "x", module_slug: "crispr", week_number: 7, year: 2026 },
      ],
    });
    fireEvent.click(screen.getByTestId("week-chip-7"));
    fireEvent.click(screen.getByTestId("skip-conflicts"));
    expect(screen.getByTestId("preview").textContent).toMatch(
      /will cancel the batch/,
    );
  });
});
