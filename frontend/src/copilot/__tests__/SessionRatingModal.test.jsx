import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import SessionRatingModal from "../SessionRatingModal";

vi.mock("../../lib/authStorage", () => ({
  default: { getToken: () => "test-token" },
  getToken: () => "test-token",
}));

function makeFetch(handler) {
  return vi.fn(async (url, opts = {}) => handler(url, opts));
}

describe("SessionRatingModal", () => {
  it("does not render when open is false", () => {
    const { container } = render(
      <SessionRatingModal sessionId="s1" open={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("Submit is disabled until a value is chosen", () => {
    render(<SessionRatingModal sessionId="s1" open={true} />);
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
  });

  it("requires comment when value is 2 or fewer", () => {
    render(<SessionRatingModal sessionId="s1" open={true} />);
    fireEvent.click(screen.getByLabelText("2 stars"));
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Session rating comment"), {
      target: { value: "bad" },
    });
    expect(screen.getByRole("button", { name: /submit/i })).not.toBeDisabled();
  });

  it("submits without comment when value is 3 or higher", async () => {
    const fetcher = makeFetch(async (url, opts) => {
      expect(url).toMatch(/\/sessions\/s1\/rating$/);
      expect(JSON.parse(opts.body)).toEqual({ value: 4 });
      return { ok: true, status: 201, json: async () => ({}) };
    });
    const onSubmitted = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onSubmitted={onSubmitted}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(screen.getByLabelText("4 stars"));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled());
  });

  it("Cancel close invokes onCancel without posting", () => {
    const fetcher = vi.fn();
    const onCancel = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onCancel={onCancel}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel close/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
