import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../../lib/api", () => {
  const list = vi.fn();
  const bulkCreate = vi.fn();
  const api = {
    admin: {
      templates: { list },
      events: { bulkCreate },
    },
  };
  return { api, default: api };
});

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

vi.mock("../../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import api from "../../../lib/api";
import { toast } from "../../../state/toast";
import BulkAddSection from "../BulkAddSection";

const MODULES = [
  { slug: "crispr-1", name: "CRISPR Module 1", type: "module", default_capacity: 30, duration_minutes: 90, deleted_at: null },
  { slug: "old", name: "Archived", type: "module", default_capacity: 20, duration_minutes: 90, deleted_at: "2026-01-01T00:00:00Z" },
  { slug: "sem", name: "A Seminar", type: "seminar", default_capacity: 10, duration_minutes: 60, deleted_at: null },
];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <BulkAddSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BulkAddSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.admin.templates.list.mockResolvedValue(MODULES);
  });

  it("lists only active module-type templates in the picker", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "CRISPR Module 1" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("option", { name: "Archived" })).toBeNull();
    expect(screen.queryByRole("option", { name: "A Seminar" })).toBeNull();
  });

  it("submits the chosen module and typed rows", async () => {
    api.admin.events.bulkCreate.mockResolvedValue({ created_count: 1, merged_count: 0, events: [] });
    renderPage();
    await waitFor(() => screen.getByRole("option", { name: "CRISPR Module 1" }));

    await userEvent.selectOptions(screen.getByLabelText(/which module/i), "crispr-1");
    await userEvent.type(screen.getByLabelText(/^school$/i), "San Marcos High School");
    // date + time inputs
    const date = document.getElementById("date-0");
    const time = document.getElementById("time-0");
    await userEvent.type(date, "2026-05-04");
    await userEvent.type(time, "09:00");

    await userEvent.click(screen.getByRole("button", { name: /create events/i }));

    await waitFor(() => expect(api.admin.events.bulkCreate).toHaveBeenCalled());
    const [slug, rows] = api.admin.events.bulkCreate.mock.calls[0];
    expect(slug).toBe("crispr-1");
    expect(rows[0]).toMatchObject({
      school: "San Marcos High School",
      date: "2026-05-04",
      start_time: "09:00",
      capacity: null,
      kind: "module",
    });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("sends kind=orientation when the row type is switched", async () => {
    api.admin.events.bulkCreate.mockResolvedValue({ created_count: 1, merged_count: 0, events: [] });
    renderPage();
    await waitFor(() => screen.getByRole("option", { name: "CRISPR Module 1" }));

    await userEvent.selectOptions(screen.getByLabelText(/which module/i), "crispr-1");
    await userEvent.type(screen.getByLabelText(/^school$/i), "San Marcos High School");
    await userEvent.type(document.getElementById("date-0"), "2026-05-04");
    await userEvent.type(document.getElementById("time-0"), "09:00");
    await userEvent.selectOptions(document.getElementById("kind-0"), "orientation");

    await userEvent.click(screen.getByRole("button", { name: /create events/i }));

    await waitFor(() => expect(api.admin.events.bulkCreate).toHaveBeenCalled());
    const [, rows] = api.admin.events.bulkCreate.mock.calls[0];
    expect(rows[0].kind).toBe("orientation");
  });

  it("shows per-row errors when the backend flags a row", async () => {
    // Validation problems come back in the 200 body (nothing created), not as a throw.
    api.admin.events.bulkCreate.mockResolvedValue({
      created_count: 0,
      merged_count: 0,
      events: [],
      errors: [{ row: 0, message: "School is required." }],
    });
    renderPage();
    await waitFor(() => screen.getByRole("option", { name: "CRISPR Module 1" }));

    await userEvent.selectOptions(screen.getByLabelText(/which module/i), "crispr-1");
    await userEvent.type(document.getElementById("date-0"), "2026-05-04");
    await userEvent.type(document.getElementById("time-0"), "09:00");
    await userEvent.click(screen.getByRole("button", { name: /create events/i }));

    expect(await screen.findByText("School is required.")).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalled();
  });
});
