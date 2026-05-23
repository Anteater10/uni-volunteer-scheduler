import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import ConfirmationCard from "../ConfirmationCard";

describe("ConfirmationCard", () => {
  it("renders tool name, args, preview, and fires onApprove/onReject", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <ConfirmationCard
        tool="send_reminder_email"
        args={{ participant_ids: [101, 134], template: "no_show" }}
        preview="Will email 2 participants"
        onApprove={onApprove}
        onReject={onReject}
      />,
    );
    expect(screen.getByText("send_reminder_email")).toBeInTheDocument();
    expect(screen.getByText(/2 participants/)).toBeInTheDocument();
    // args are JSON-serialised into a <pre>
    expect(screen.getByText(/no_show/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Confirm"));
    expect(onApprove).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("Reject"));
    expect(onReject).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons when disabled prop is true", () => {
    render(
      <ConfirmationCard
        tool="t"
        args={{}}
        preview=""
        onApprove={() => {}}
        onReject={() => {}}
        disabled
      />,
    );
    expect(screen.getByText("Confirm")).toBeDisabled();
    expect(screen.getByText("Reject")).toBeDisabled();
  });

  it("renders without a preview line when preview is falsy", () => {
    const { container } = render(
      <ConfirmationCard
        tool="t"
        args={{ k: "v" }}
        onApprove={() => {}}
        onReject={() => {}}
      />,
    );
    expect(container.querySelector("p")).toBeNull();
  });
});
