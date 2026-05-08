// src/components/__tests__/OrientationWarningModal.test.jsx
//
// Tests for OrientationWarningModal: render, button callbacks, closed state.
// 4 test cases.

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import OrientationWarningModal from "../OrientationWarningModal";

function renderModal(props = {}) {
  const defaults = {
    open: true,
    onYes: vi.fn(),
    onNo: vi.fn(),
  };
  return render(<OrientationWarningModal {...defaults} {...props} />);
}

describe("OrientationWarningModal", () => {
  // -------------------------------------------------------------------------
  // Test 11: Renders modal with title and two buttons when open=true
  // -------------------------------------------------------------------------
  it("renders modal title and both buttons when open=true", () => {
    renderModal();

    expect(
      screen.getByText(/have you done a sci trek orientation/i)
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: /i've done orientation/i })
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: /i haven't.*show me orientation events/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 12: Does not render when open=false
  // -------------------------------------------------------------------------
  it("does not render when open=false", () => {
    renderModal({ open: false });

    expect(
      screen.queryByText(/have you done a sci trek orientation/i)
    ).not.toBeInTheDocument();

    expect(
      screen.queryByRole("button", { name: /yes/i })
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 13: Clicking "Yes" calls onYes
  // -------------------------------------------------------------------------
  it("calls onYes when Yes button is clicked", () => {
    const onYes = vi.fn();
    renderModal({ onYes });

    fireEvent.click(
      screen.getByRole("button", { name: /i've done orientation/i })
    );

    expect(onYes).toHaveBeenCalledTimes(1);
  });

  // -------------------------------------------------------------------------
  // Test 14: Clicking "No" calls onNo
  // -------------------------------------------------------------------------
  it("calls onNo when No button is clicked", () => {
    const onNo = vi.fn();
    renderModal({ onNo });

    fireEvent.click(
      screen.getByRole("button", { name: /i haven't.*show me orientation events/i })
    );

    expect(onNo).toHaveBeenCalledTimes(1);
  });
});
