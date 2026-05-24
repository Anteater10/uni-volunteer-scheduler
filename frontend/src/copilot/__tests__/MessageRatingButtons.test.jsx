import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import MessageRatingButtons from "../MessageRatingButtons";

vi.mock("../../lib/authStorage", () => ({
  default: { getToken: () => "test-token" },
  getToken: () => "test-token",
}));

function makeFetch(handler) {
  return vi.fn(async (url, opts = {}) => handler(url, opts));
}

describe("MessageRatingButtons", () => {
  it("renders nothing without a messageId", () => {
    const { container } = render(<MessageRatingButtons />);
    expect(container.firstChild).toBeNull();
  });

  it("posts immediately on thumbs-up", async () => {
    const fetcher = makeFetch(async (url, opts) => {
      expect(url).toMatch(/\/messages\/m1\/rating$/);
      expect(JSON.parse(opts.body)).toEqual({ value: "up" });
      return { ok: true, status: 200, json: async () => ({}) };
    });
    render(<MessageRatingButtons messageId="m1" fetcher={fetcher} />);
    fireEvent.click(screen.getByLabelText("Thumbs up"));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  });

  it("reveals textarea on thumbs-down, blocks submit until non-empty", async () => {
    const fetcher = makeFetch(async () => ({
      ok: true,
      status: 200,
      json: async () => ({}),
    }));
    render(<MessageRatingButtons messageId="m1" fetcher={fetcher} />);
    fireEvent.click(screen.getByLabelText("Thumbs down"));
    expect(fetcher).not.toHaveBeenCalled();
    const submit = screen.getByRole("button", { name: /submit/i });
    expect(submit).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText(/Comment for thumbs-down/i),
      { target: { value: "wrong week" } },
    );
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    const [, opts] = fetcher.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({
      value: "down",
      comment: "wrong week",
    });
  });

  it("switching from up to down clears prior active state until comment is submitted", async () => {
    const fetcher = makeFetch(async () => ({
      ok: true,
      status: 200,
      json: async () => ({}),
    }));
    render(<MessageRatingButtons messageId="m1" fetcher={fetcher} />);
    fireEvent.click(screen.getByLabelText("Thumbs up"));
    await waitFor(() =>
      expect(screen.getByLabelText("Thumbs up")).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    fireEvent.click(screen.getByLabelText("Thumbs down"));
    expect(screen.getByLabelText("Thumbs up")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByLabelText("Thumbs down")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("surfaces an error message on non-2xx response", async () => {
    const fetcher = makeFetch(async () => ({
      ok: false,
      status: 500,
      json: async () => ({}),
    }));
    render(<MessageRatingButtons messageId="m1" fetcher={fetcher} />);
    fireEvent.click(screen.getByLabelText("Thumbs up"));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/HTTP 500/),
    );
  });
});
