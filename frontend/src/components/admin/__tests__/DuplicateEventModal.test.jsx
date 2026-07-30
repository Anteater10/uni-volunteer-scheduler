import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Declared before component imports so vi.mock hoisting works.
vi.mock("../../../lib/api", () => {
  const apiMock = {
    events: {
      create: vi.fn(async () => ({ id: "ev-new" })),
      list: vi.fn(async () => []),
    },
    slots: {
      create: vi.fn(async () => ({})),
      update: vi.fn(async () => ({})),
      delete: vi.fn(async () => ({})),
    },
    admin: {
      modules: { list: vi.fn(async () => [{ slug: "crispr-1", name: "CRISPR" }]) },
    },
    public: {
      listEvents: vi.fn(async () => []),
      getQuarters: vi.fn(async () => []),
    },
  };
  return { default: apiMock, api: apiMock };
});

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("../../../state/toast", () => ({ toast: toastMock }));

import { within } from "@testing-library/react";

import { api } from "../../../lib/api";
import DuplicateEventModal from "../DuplicateEventModal";

const SPRING = {
  id: "q-spring",
  season: "spring",
  year: 2026,
  start_date: "2026-03-30",
  end_date: "2026-06-14",
  weeks_in_quarter: 11,
  display_name: "Spring 2026",
  archived_at: "2026-06-20T00:00:00Z",
};

const FALL = {
  id: "q-fall",
  season: "fall",
  year: 2026,
  start_date: "2026-09-28",
  end_date: "2026-12-13",
  weeks_in_quarter: 11,
  display_name: "Fall 2026",
  archived_at: null,
};

// Ended but never archived — the gap activeQuarters() doesn't close. Picking
// this as a target would now 422 QUARTER_READONLY server-side (create_event
// gates the derived/target quarter), so the modal excludes it too.
const WINTER_ENDED_UNARCHIVED = {
  id: "q-winter-ended",
  season: "winter",
  year: 2020,
  start_date: "2020-01-06",
  end_date: "2020-03-15",
  weeks_in_quarter: 10,
  display_name: "Winter 2020",
  archived_at: null,
};

// Mid-day UTC times so local-date derivation can't drift a day in any
// test-runner timezone.
const SOURCE = {
  id: "ev-src",
  title: "CRISPR at Franklin",
  description: "Original run",
  location: "Room 12",
  school: "Franklin Elementary",
  visibility: "public",
  max_signups_per_user: null,
  module_slug: "crispr-1",
  quarter_id: "q-spring",
  week_number: 3,
  start_date: "2026-04-15T12:00:00Z",
  end_date: "2026-04-15T16:00:00Z",
  slots: [
    {
      id: "slot-1",
      slot_type: "period",
      start_time: "2026-04-15T13:00:00Z",
      end_time: "2026-04-15T14:00:00Z",
      capacity: 4,
      location: "Room 13",
      current_count: 3,
    },
  ],
};

function plusDaysLocal(iso, days) {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d;
}

function renderModal(props = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DuplicateEventModal
          open
          sourceEvent={SOURCE}
          quarters={[SPRING, FALL]}
          onClose={props.onClose || vi.fn()}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DuplicateEventModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("defaults to the current/upcoming quarter and mirrors the source week, prefilled and shifted", async () => {
    renderModal();

    expect(
      screen.getByText(/Duplicate "CRISPR at Franklin"/i),
    ).toBeInTheDocument();

    // Spring is archived → Fall is the default target; week mirrors wk 3.
    expect(screen.getByLabelText("Target quarter")).toHaveValue("q-fall");
    expect(screen.getByLabelText("Target week")).toHaveValue("3");

    // Spring wk3 → Fall wk3 = +182 days: Apr 15 lands on Oct 14.
    expect(screen.getByLabelText("Title *")).toHaveValue("CRISPR at Franklin");
    expect(screen.getByLabelText("Start *").value.slice(0, 10)).toBe("2026-10-14");
    expect(screen.getByLabelText("Slot 1 date")).toHaveValue("2026-10-14");
    expect(screen.getByLabelText("Slot 1 capacity")).toHaveValue(4);
    expect(screen.getByLabelText("Slot 1 location")).toHaveValue("Room 13");
  });

  it("re-applies suggested dates when the target week changes", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.selectOptions(screen.getByLabelText("Target week"), "4");
    expect(screen.getByLabelText("Start *").value.slice(0, 10)).toBe("2026-10-21");
    expect(screen.getByLabelText("Slot 1 date")).toHaveValue("2026-10-21");
  });

  it("creates through the normal event-create path with source_event_id", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderModal({ onClose });

    await user.click(screen.getByRole("button", { name: "Create event" }));

    await waitFor(() => expect(api.events.create).toHaveBeenCalledTimes(1));
    const payload = api.events.create.mock.calls[0][0];
    expect(payload.source_event_id).toBe("ev-src");
    expect(payload.title).toBe("CRISPR at Franklin");
    expect(payload.module_slug).toBe("crispr-1");
    expect(new Date(payload.start_date).toISOString()).toBe(
      plusDaysLocal(SOURCE.start_date, 182).toISOString(),
    );
    expect(payload.slots).toHaveLength(1);
    expect(payload.slots[0].capacity).toBe(4);
    expect(new Date(payload.slots[0].start_time).toISOString()).toBe(
      plusDaysLocal("2026-04-15T13:00:00Z", 182).toISOString(),
    );

    await waitFor(() => expect(toastMock.success).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it("warns (without blocking) when the target week already has this module", async () => {
    api.public.listEvents.mockResolvedValueOnce([
      {
        id: "other-ev",
        title: "Existing run",
        module_slug: "crispr-1",
        week_number: 3,
      },
    ]);
    renderModal();

    expect(await screen.findByText(/already has/i)).toBeInTheDocument();
    expect(api.public.listEvents).toHaveBeenCalledWith({
      quarter_id: "q-fall",
      week_number: 3,
    });
    // The create button stays enabled — the admin decides.
    expect(screen.getByRole("button", { name: "Create event" })).toBeEnabled();
  });

  it("excludes ended (but not yet archived) quarters from the target picker", () => {
    renderModal({ quarters: [SPRING, FALL, WINTER_ENDED_UNARCHIVED] });

    const labels = within(screen.getByLabelText("Target quarter"))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(labels).toContain("Fall 2026");
    expect(labels).not.toContain("Winter 2020");
  });
});
