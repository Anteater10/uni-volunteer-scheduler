// Phase 24 — ReminderPreferencesCard tests
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../lib/api", () => {
  const getPreferences = vi.fn();
  const updatePreferences = vi.fn();
  const api = {
    public: {
      getPreferences,
      updatePreferences,
    },
  };
  return { api, default: api };
});

vi.mock("../../state/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { api } from "../../lib/api";
import ReminderPreferencesCard from "../ReminderPreferencesCard";

describe("ReminderPreferencesCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the toggle in 'on' state when the server returns enabled=true", async () => {
    api.public.getPreferences.mockResolvedValueOnce({
      volunteer_email: "vee@example.com",
      email_reminders_enabled: true,
      sms_opt_in: false,
      phone_e164: null,
      created_at: "2026-04-17T00:00:00Z",
      updated_at: "2026-04-17T00:00:00Z",
    });

    render(<ReminderPreferencesCard manageToken="abc123abc123abc" />);

    await waitFor(() =>
      expect(api.public.getPreferences).toHaveBeenCalledWith("abc123abc123abc")
    );
    const checkbox = await screen.findByRole("checkbox", {
      name: /send me reminder emails/i,
    });
    expect(checkbox).toBeChecked();
  });

  it("sends a PUT when the toggle is flipped off", async () => {
    api.public.getPreferences.mockResolvedValueOnce({
      volunteer_email: "vee@example.com",
      email_reminders_enabled: true,
      sms_opt_in: false,
      phone_e164: null,
      created_at: "2026-04-17T00:00:00Z",
      updated_at: "2026-04-17T00:00:00Z",
    });
    api.public.updatePreferences.mockResolvedValueOnce({
      volunteer_email: "vee@example.com",
      email_reminders_enabled: false,
      sms_opt_in: false,
      phone_e164: null,
      created_at: "2026-04-17T00:00:00Z",
      updated_at: "2026-04-17T00:00:00Z",
    });

    render(<ReminderPreferencesCard manageToken="abc123abc123abc" />);
    const checkbox = await screen.findByRole("checkbox", {
      name: /send me reminder emails/i,
    });
    await userEvent.click(checkbox);

    await waitFor(() =>
      expect(api.public.updatePreferences).toHaveBeenCalledWith(
        "abc123abc123abc",
        { email_reminders_enabled: false }
      )
    );
  });
});
