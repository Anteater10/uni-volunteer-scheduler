// Issue #24 — QuartersSection: the admin enters season/year/label and the
// two dates from the UCSB calendar; weeks self-populate; saves surface the
// relink summary.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const listMock = vi.fn();
const createMock = vi.fn();
const updateMock = vi.fn();
const removeMock = vi.fn();
const archiveMock = vi.fn();
const restoreMock = vi.fn();

vi.mock("../../../lib/api", () => ({
  default: {
    admin: {
      quarters: {
        list: (...a) => listMock(...a),
        create: (...a) => createMock(...a),
        update: (...a) => updateMock(...a),
        remove: (...a) => removeMock(...a),
        archive: (...a) => archiveMock(...a),
        restore: (...a) => restoreMock(...a),
      },
    },
  },
}));

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

import QuartersSection from "../QuartersSection";

const SPRING = {
  id: "spring-26",
  season: "spring",
  year: 2026,
  label: "",
  start_date: "2026-03-30",
  end_date: "2026-06-14",
  weeks_in_quarter: 11,
  display_name: "Spring 2026",
  archived_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// Dates relative to the real clock — "Archive" is offered only for rows
// that have already ended.
const iso = (d) => d.toISOString().slice(0, 10);
const NOW = new Date();
const CURRENT = {
  ...SPRING,
  id: "current-q",
  season: "fall",
  display_name: "Current quarter",
  start_date: iso(new Date(NOW.getTime() - 30 * 86400000)),
  end_date: iso(new Date(NOW.getTime() + 40 * 86400000)),
};
const ARCHIVED = {
  ...SPRING,
  id: "winter-26",
  season: "winter",
  display_name: "Winter 2026",
  start_date: "2026-01-05",
  end_date: "2026-03-20",
  archived_at: "2026-07-01T00:00:00Z",
};

function renderPage(initialEntries = ["/admin/quarters"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <QuartersSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("QuartersSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue([SPRING]);
    createMock.mockResolvedValue({
      quarter: { ...SPRING, id: "new-q", display_name: "Fall 2026" },
      relink_summary: { linked: 2, weeks_changed: 1, unlinked: 0 },
    });
    updateMock.mockResolvedValue({
      quarter: SPRING,
      relink_summary: { linked: 1, weeks_changed: 0, unlinked: 1 },
    });
    removeMock.mockResolvedValue(undefined);
  });

  it("lists entered quarters with their week counts", async () => {
    renderPage();
    expect(await screen.findByText("Spring 2026")).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
  });

  it("shows the setup callout when no quarters exist", async () => {
    listMock.mockResolvedValue([]);
    renderPage(["/admin/quarters?setup=1"]);
    expect(await screen.findByText(/enter your quarters/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ucsb academic calendar/i })).toBeInTheDocument();
  });

  it("creates a quarter from the two dates with a live weeks preview", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("add-quarter"));

    fireEvent.change(screen.getByLabelText(/season/i), { target: { value: "fall" } });
    fireEvent.change(screen.getByLabelText(/year/i), { target: { value: "2026" } });
    fireEvent.change(screen.getByLabelText(/quarter begins/i), {
      target: { value: "2026-09-21" },
    });
    fireEvent.change(screen.getByLabelText(/quarter ends/i), {
      target: { value: "2026-12-06" },
    });

    // Weeks self-populate from the dates — no week input anywhere.
    expect(screen.getByTestId("weeks-preview").textContent).toMatch(/11 weeks/);

    fireEvent.click(screen.getByTestId("save-quarter"));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect(createMock).toHaveBeenCalledWith({
      season: "fall",
      year: 2026,
      label: "",
      start_date: "2026-09-21",
      end_date: "2026-12-06",
    });
  });

  it("confirms before saving a date change (recategorizes events)", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("edit-spring-26"));

    fireEvent.change(screen.getByLabelText(/quarter ends/i), {
      target: { value: "2026-06-07" },
    });
    fireEvent.click(screen.getByTestId("save-quarter"));

    // Update is gated behind the confirm modal.
    expect(updateMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("confirm-save"));
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    expect(updateMock).toHaveBeenCalledWith("spring-26", {
      season: "spring",
      year: 2026,
      label: "",
      start_date: "2026-03-30",
      end_date: "2026-06-07",
    });
  });

  it("deletes after confirmation", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("delete-spring-26"));
    fireEvent.click(screen.getByTestId("confirm-delete"));
    await waitFor(() => expect(removeMock).toHaveBeenCalledWith("spring-26"));
  });

  // ---- issue #33: archive / restore ----

  it("offers Archive only for quarters that have already ended", async () => {
    listMock.mockResolvedValue([SPRING, CURRENT]);
    renderPage();
    expect(await screen.findByTestId("archive-spring-26")).toBeInTheDocument();
    expect(screen.queryByTestId("archive-current-q")).toBeNull();
  });

  it("archives a past quarter after confirmation", async () => {
    archiveMock.mockResolvedValue({ ...SPRING, archived_at: "2026-07-16T00:00:00Z" });
    renderPage();
    fireEvent.click(await screen.findByTestId("archive-spring-26"));

    expect(archiveMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("confirm-archive"));
    await waitFor(() => expect(archiveMock).toHaveBeenCalledWith("spring-26"));
  });

  // ---- issue #38: retrospective drill-in ----

  it("offers a View events link for past and archived quarters but not the current one", async () => {
    listMock.mockResolvedValue([SPRING, CURRENT, ARCHIVED]);
    renderPage();

    expect(await screen.findByTestId("retro-spring-26")).toHaveAttribute(
      "href",
      "/admin/quarters/spring-26",
    );
    expect(screen.getByTestId("retro-winter-26")).toHaveAttribute(
      "href",
      "/admin/quarters/winter-26",
    );
    expect(screen.queryByTestId("retro-current-q")).toBeNull();
  });

  it("shows an Archived chip and a Restore action for archived rows", async () => {
    listMock.mockResolvedValue([ARCHIVED]);
    restoreMock.mockResolvedValue({ ...ARCHIVED, archived_at: null });
    renderPage();

    expect(await screen.findByText("Archived")).toBeInTheDocument();
    expect(screen.queryByTestId("archive-winter-26")).toBeNull();

    fireEvent.click(screen.getByTestId("restore-winter-26"));
    await waitFor(() => expect(restoreMock).toHaveBeenCalledWith("winter-26"));
  });
});
