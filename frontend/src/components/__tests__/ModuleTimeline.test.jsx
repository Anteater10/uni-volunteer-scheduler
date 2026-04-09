import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ModuleTimeline from "../ModuleTimeline";

function renderTimeline(modules) {
  return render(
    <MemoryRouter>
      <ModuleTimeline modules={modules} />
    </MemoryRouter>,
  );
}

describe("ModuleTimeline", () => {
  it("renders completed module with checkmark", () => {
    renderTimeline([
      { slug: "orientation", name: "Orientation", status: "completed", override_active: false, last_activity: null },
    ]);
    expect(screen.getByText("Orientation")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders locked module with reduced opacity", () => {
    renderTimeline([
      { slug: "intro-bio", name: "Intro to Biology", status: "locked", override_active: false, last_activity: null },
    ]);
    const listItem = screen.getByText("Intro to Biology").closest("li");
    expect(listItem.className).toContain("opacity-50");
  });

  it("shows override badge when override_active is true", () => {
    renderTimeline([
      { slug: "orientation", name: "Orientation", status: "unlocked", override_active: true, last_activity: null },
    ]);
    expect(screen.getByText("Override active")).toBeInTheDocument();
  });

  it("renders nothing when modules array is empty", () => {
    const { container } = renderTimeline([]);
    expect(container.innerHTML).toBe("");
  });
});
