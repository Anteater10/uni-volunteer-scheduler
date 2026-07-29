import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Declared before component imports so vi.mock hoisting works.
vi.mock("../../../lib/api", () => {
  const apiMock = {
    events: {
      update: vi.fn(async () => ({})),
      list: vi.fn(async () => []),
    },
    slots: {
      create: vi.fn(async () => ({})),
      update: vi.fn(async () => ({})),
      delete: vi.fn(async () => ({})),
    },
    admin: { modules: { list: vi.fn(async () => []) } },
    public: { getQuarters: vi.fn(async () => []) },
  };
  return { default: apiMock, api: apiMock };
});

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("../../../state/toast", () => ({ toast: toastMock }));

import { api } from "../../../lib/api";
import EventSettingsModal from "../EventSettingsModal";

// A complete event: the form legitimately refuses to save without a module
// and at least one valid slot, so the fixture has to satisfy both. Times sit
// mid-day UTC so the local dates the form derives don't shift timezone to
// timezone and drift outside the event window.
const EVENT = {
  id: "ev-1",
  title: "CRISPR Module 1",
  description: "Three-day residency",
  location: "GVJH — Room 12",
  school: "Goleta Valley Junior High",
  module_slug: "crispr-1",
  start_date: "2026-07-26T12:00:00Z",
  end_date: "2026-07-30T12:00:00Z",
  visibility: "public",
  max_signups_per_user: null,
  slots: [
    {
      id: "slot-1",
      slot_type: "period",
      start_time: "2026-07-27T12:00:00Z",
      end_time: "2026-07-27T15:00:00Z",
      capacity: 5,
      location: "GVJH — Room 12",
      current_count: 0,
    },
  ],
};

function renderModal(props = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <EventSettingsModal
          open
          event={EVENT}
          onClose={props.onClose || vi.fn()}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventSettingsModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nothing when closed", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EventSettingsModal open={false} event={EVENT} onClose={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the event hasn't loaded yet", () => {
    // The page passes eventQ.data straight through, which is undefined on the
    // first render — that must not blow up on event.id.
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EventSettingsModal open event={undefined} onClose={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("seeds the form with the event's current details", () => {
    renderModal();
    expect(screen.getByText("Event settings")).toBeInTheDocument();
    expect(screen.getByDisplayValue("CRISPR Module 1")).toBeInTheDocument();
    // Location shows twice — once for the event, once on the slot that
    // inherited it — so assert on the count rather than a single match.
    expect(screen.getAllByDisplayValue("GVJH — Room 12")).toHaveLength(2);
  });

  it("PATCHes the event and closes on save", async () => {
    const onClose = vi.fn();
    renderModal({ onClose });

    const title = screen.getByDisplayValue("CRISPR Module 1");
    await userEvent.clear(title);
    await userEvent.type(title, "CRISPR Module 2");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(api.events.update).toHaveBeenCalledTimes(1));
    expect(api.events.update).toHaveBeenCalledWith(
      "ev-1",
      expect.objectContaining({ title: "CRISPR Module 2" }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toastMock.success).toHaveBeenCalled();
  });

  it("reports a failed save and stays open", async () => {
    api.events.update.mockRejectedValueOnce(new Error("Conflict"));
    const onClose = vi.fn();
    renderModal({ onClose });

    const title = screen.getByDisplayValue("CRISPR Module 1");
    await userEvent.type(title, "x");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith("Conflict"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes without saving when cancelled", async () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
    expect(api.events.update).not.toHaveBeenCalled();
  });
});
