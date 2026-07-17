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

vi.mock("../../../lib/api", () => ({
  default: {
    admin: {
      quarters: {
        list: (...a) => listMock(...a),
        create: (...a) => createMock(...a),
        update: (...a) => updateMock(...a),
        remove: (...a) => removeMock(...a),
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
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
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
});
