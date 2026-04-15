import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import SideDrawer from "../SideDrawer";

describe("SideDrawer", () => {
  it("renders title and children when open", () => {
    render(
      <SideDrawer open onClose={() => {}} title="Details">
        <p>Body content</p>
      </SideDrawer>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Details")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
  });

  it("calls onClose on Escape key", () => {
    const onClose = vi.fn();
    render(
      <SideDrawer open onClose={onClose} title="Details">
        <p>Body</p>
      </SideDrawer>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when backdrop is clicked", () => {
    const onClose = vi.fn();
    render(
      <SideDrawer open onClose={onClose} title="Details">
        <p>Body</p>
      </SideDrawer>,
    );
    fireEvent.click(screen.getByTestId("side-drawer-backdrop"));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders nothing when open=false", () => {
    const { container } = render(
      <SideDrawer open={false} onClose={() => {}} title="Details">
        <p>Body</p>
      </SideDrawer>,
    );
    expect(container.firstChild).toBeNull();
  });
});
