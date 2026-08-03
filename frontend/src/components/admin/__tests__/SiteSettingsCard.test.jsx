// src/components/admin/__tests__/SiteSettingsCard.test.jsx
//
// Task 10 — SiteSettingsCard grows a "Volunteer contact email" field so
// admins can set the address volunteers are told to use for schedule
// changes/cancellations now that self-service cancel/swap is gone.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../../lib/api", () => {
  const apiMock = {
    admin: {
      siteSettings: {
        get: vi.fn(),
        update: vi.fn(),
      },
    },
  };
  return { default: apiMock, api: apiMock };
});

import { api } from "../../../lib/api";
import SiteSettingsCard from "../SiteSettingsCard";

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SiteSettingsCard />
    </QueryClientProvider>,
  );
}

describe("SiteSettingsCard — contact email", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.admin.siteSettings.get.mockResolvedValue({
      hide_past_events_from_public: true,
      show_audit_logs_tab: false,
      contact_email: "old@ucsb.edu",
    });
    api.admin.siteSettings.update.mockResolvedValue({
      contact_email: "scitrek@ucsb.edu",
    });
  });

  it("loads the existing contact email into the input", async () => {
    renderCard();
    const input = await screen.findByLabelText(/volunteer contact email/i);
    // The field renders immediately (disabled) while the query is still
    // in flight, so wait for the fetched value rather than asserting
    // right after the element first appears.
    await waitFor(() => expect(input).toHaveValue("old@ucsb.edu"));
  });

  it("keeps the save button disabled until the value is edited", async () => {
    renderCard();
    await screen.findByLabelText(/volunteer contact email/i);
    expect(screen.getByRole("button", { name: /save contact/i })).toBeDisabled();
  });

  it("edits and saves the volunteer contact email", async () => {
    renderCard();
    const input = await screen.findByLabelText(/volunteer contact email/i);
    fireEvent.change(input, { target: { value: "scitrek@ucsb.edu" } });
    expect(screen.getByRole("button", { name: /save contact/i })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: /save contact/i }));
    await waitFor(() =>
      expect(api.admin.siteSettings.update).toHaveBeenCalledWith({
        contact_email: "scitrek@ucsb.edu",
      }),
    );
  });

  it("supports clearing the contact email back to blank", async () => {
    renderCard();
    const input = await screen.findByLabelText(/volunteer contact email/i);
    await waitFor(() => expect(input).toHaveValue("old@ucsb.edu"));
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /save contact/i }));
    await waitFor(() =>
      expect(api.admin.siteSettings.update).toHaveBeenCalledWith({
        contact_email: "",
      }),
    );
  });
});
