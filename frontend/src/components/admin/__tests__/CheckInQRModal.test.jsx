// src/components/admin/__tests__/CheckInQRModal.test.jsx
//
// Issue #31 hardening — the check-in QR URL carries the event's venue code
// (?v=CODE) so the public lookup/selected endpoints can gate on it. The
// modal fetches the roster (which lazily generates + persists the code) and
// only renders the QR once the code is known.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../../api/roster", () => ({
  fetchRoster: vi.fn(),
}));

import { fetchRoster } from "../../../api/roster";
import CheckInQRModal from "../CheckInQRModal";

function renderModal(props = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CheckInQRModal
        open
        onClose={() => {}}
        eventId="evt-1"
        eventTitle="Bio @ Lincoln"
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("CheckInQRModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("embeds the venue code in the check-in URL once the roster resolves", async () => {
    fetchRoster.mockResolvedValue({ event_id: "evt-1", venue_code: "4321" });

    renderModal();

    const link = await screen.findByRole("link", { name: /event-check-in/i });
    expect(link).toHaveAttribute(
      "href",
      expect.stringContaining("/event-check-in/evt-1?v=4321"),
    );
    expect(fetchRoster).toHaveBeenCalledWith("evt-1");
  });

  it("shows the venue code as a typed fallback for the organizer", async () => {
    fetchRoster.mockResolvedValue({ event_id: "evt-1", venue_code: "4321" });

    renderModal();

    expect(
      await screen.findByText("4321", { selector: "strong" }),
    ).toBeInTheDocument();
  });

  it("shows a loading state until the code is known", async () => {
    let resolve;
    fetchRoster.mockReturnValue(new Promise((r) => (resolve = r)));

    renderModal();

    expect(screen.getByText(/preparing check-in code/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /event-check-in/i })).not.toBeInTheDocument();

    resolve({ event_id: "evt-1", venue_code: "9876" });
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /event-check-in/i })).toBeInTheDocument(),
    );
  });

  it("shows an error when the roster fetch fails", async () => {
    fetchRoster.mockRejectedValue(new Error("boom"));

    renderModal();

    expect(
      await screen.findByText(/couldn't load the check-in code/i),
    ).toBeInTheDocument();
  });
});
