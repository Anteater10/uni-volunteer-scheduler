import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CopilotMemorySettings from "../CopilotMemorySettings";

vi.mock("../../lib/authStorage", () => ({
  default: { getToken: () => "test-token" },
  getToken: () => "test-token",
}));

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

beforeEach(() => {
  global.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CopilotMemorySettings", () => {
  it("shows loading state then empty-state copy when profile is empty", async () => {
    let resolveGet;
    global.fetch.mockImplementationOnce(
      () =>
        new Promise((res) => {
          resolveGet = () =>
            res(
              jsonResponse({
                profile_text: "",
                updated_at: null,
                version: 0,
              }),
            );
        }),
    );

    render(<CopilotMemorySettings />);
    expect(screen.getByText(/Loading profile/i)).toBeInTheDocument();

    resolveGet();
    await waitFor(() => {
      expect(
        screen.getByText(/hasn't learned anything stable about you yet/i),
      ).toBeInTheDocument();
    });

    // Forget button is disabled when there's nothing to forget.
    const btn = screen.getByRole("button", {
      name: /forget what you know about me/i,
    });
    expect(btn).toBeDisabled();
  });

  it("renders profile text + last updated timestamp when populated", async () => {
    global.fetch.mockResolvedValueOnce(
      jsonResponse({
        profile_text: "Prefers short answers. Works in admin role.",
        updated_at: "2026-05-20T18:30:00Z",
        version: 4,
      }),
    );

    render(<CopilotMemorySettings />);
    await waitFor(() => {
      expect(
        screen.getByText(/Prefers short answers\. Works in admin role\./),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/Last updated:/i)).toBeInTheDocument();
  });

  it("Forget → confirm → DELETE called → empty state appears", async () => {
    global.fetch
      .mockResolvedValueOnce(
        jsonResponse({
          profile_text: "Some learned facts.",
          updated_at: "2026-05-20T18:30:00Z",
          version: 2,
        }),
      )
      .mockResolvedValueOnce({ ok: true, status: 204, json: async () => ({}) })
      .mockResolvedValueOnce(
        jsonResponse({ profile_text: "", updated_at: null, version: 3 }),
      );

    render(<CopilotMemorySettings />);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/Some learned facts\./)).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /forget what you know about me/i }),
    );

    // Modal opens with confirm button labelled "Forget".
    const confirmBtn = await screen.findByRole("button", { name: /^Forget$/ });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/hasn't learned anything stable about you yet/i),
      ).toBeInTheDocument();
    });

    // Three fetch calls: initial GET, DELETE, refetch GET.
    expect(global.fetch).toHaveBeenCalledTimes(3);
    const deleteCall = global.fetch.mock.calls[1];
    expect(deleteCall[0]).toMatch(/\/copilot\/profile$/);
    expect(deleteCall[1]).toMatchObject({ method: "DELETE" });
  });

  it("Cancel on confirm modal does NOT call DELETE", async () => {
    global.fetch.mockResolvedValueOnce(
      jsonResponse({
        profile_text: "Stuff.",
        updated_at: "2026-05-20T18:30:00Z",
        version: 1,
      }),
    );

    render(<CopilotMemorySettings />);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/Stuff\./)).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /forget what you know about me/i }),
    );
    const cancelBtn = await screen.findByRole("button", { name: /^Cancel$/ });
    await user.click(cancelBtn);

    // Only the initial GET happened.
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Stuff\./)).toBeInTheDocument();
  });
});
