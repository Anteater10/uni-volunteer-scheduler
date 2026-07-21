import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DuplicateEventDrawer from "../DuplicateEventDrawer";

// Issue #24: duplication targets an admin-entered quarter row — weeks come
// from the row's real length and the payload carries target_quarter_id.

const SPRING = {
  id: "spring-26",
  season: "spring",
  year: 2026,
  label: "",
  start_date: "2026-03-30",
  end_date: "2026-06-14",
  weeks_in_quarter: 11,
  display_name: "Spring 2026",
  archived_at: null,
};
const SESSION_A = {
  id: "summer-26-a",
  season: "summer",
  year: 2026,
  label: "Session A",
  start_date: "2026-06-22",
  end_date: "2026-07-31",
  weeks_in_quarter: 6,
  display_name: "Summer 2026 · Session A",
  archived_at: null,
};
const QUARTERS = [SPRING, SESSION_A];

const SOURCE = {
  id: "src-1",
  title: "CRISPR Lab",
  module_slug: "crispr",
  quarter: "spring",
  year: 2026,
  week_number: 4,
  quarter_id: "spring-26",
};

function renderDrawer(props = {}) {
  const defaults = {
    open: true,
    onClose: () => {},
    sourceEvent: SOURCE,
    existingEvents: [],
    quarters: QUARTERS,
    onSubmit: vi.fn(),
    submitting: false,
  };
  return render(<DuplicateEventDrawer {...defaults} {...props} />);
}

describe("DuplicateEventDrawer", () => {
  it("renders the target row's real week count and highlights conflicts", () => {
    renderDrawer({
      existingEvents: [
        { id: "x", module_slug: "crispr", week_number: 7, year: 2026, quarter_id: "spring-26" },
      ],
    });
    const chips = screen.getAllByTestId(/week-chip-/);
    expect(chips.length).toBe(11);

    expect(screen.getByTestId("week-chip-7").getAttribute("data-conflict")).toBe("true");
    // Source's own week is an implicit conflict in its own quarter row.
    expect(screen.getByTestId("week-chip-4").getAttribute("data-conflict")).toBe("true");
    expect(screen.getByTestId("week-chip-5").getAttribute("data-conflict")).toBe("false");
  });

  it("switching to a 6-week session renders 6 chips and clears the implicit conflict", () => {
    renderDrawer();
    fireEvent.click(screen.getByTestId("quarter-chip-summer-26-a"));
    const chips = screen.getAllByTestId(/week-chip-/);
    expect(chips.length).toBe(6);
    expect(screen.getByTestId("week-chip-4").getAttribute("data-conflict")).toBe("false");
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
        { id: "x", module_slug: "crispr", week_number: 7, year: 2026, quarter_id: "spring-26" },
      ],
    });
    fireEvent.click(screen.getByTestId("week-chip-5"));
    fireEvent.click(screen.getByTestId("week-chip-7"));
    const preview = screen.getByTestId("preview");
    expect(preview.textContent).toMatch(/Creating 1 event/);
    expect(preview.textContent).toMatch(/1 conflict/);
    expect(preview.textContent).toMatch(/will be skipped/);
  });

  it("submits with target_quarter_id and the row's year", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ created: [], skipped_conflicts: [] });
    renderDrawer({ onSubmit });

    fireEvent.click(screen.getByTestId("quarter-chip-summer-26-a"));
    fireEvent.click(screen.getByTestId("week-chip-1"));
    fireEvent.click(screen.getByTestId("week-chip-2"));
    fireEvent.click(screen.getByTestId("submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      target_weeks: [1, 2],
      target_year: 2026,
      target_quarter_id: "summer-26-a",
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
        { id: "x", module_slug: "crispr", week_number: 7, year: 2026, quarter_id: "spring-26" },
      ],
    });
    fireEvent.click(screen.getByTestId("week-chip-7"));
    fireEvent.click(screen.getByTestId("skip-conflicts"));
    expect(screen.getByTestId("preview").textContent).toMatch(/will cancel the batch/);
  });
});
