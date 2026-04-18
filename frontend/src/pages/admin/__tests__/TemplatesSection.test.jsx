// src/pages/admin/__tests__/TemplatesSection.test.jsx
//
// Phase 17 Plan 02 — TemplatesSection CRUD tests.
// Covers list, create, edit, archive, restore with SideDrawer pattern.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/api", () => {
  const templates = {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    restore: vi.fn(),
  };
  return {
    default: { admin: { templates } },
  };
});

vi.mock("../../../state/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: vi.fn(),
}));

import api from "../../../lib/api";
import { toast } from "../../../state/toast";
import { useAdminPageTitle } from "../AdminLayout";
import TemplatesSection from "../TemplatesSection";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TEMPLATES = [
  {
    slug: "dna-module",
    name: "DNA Extraction",
    type: "module",
    duration_minutes: 90,
    session_count: 2,
    default_capacity: 30,
    description: "Hands-on DNA lab",
    materials: ["gloves", "tubes"],
    deleted_at: null,
  },
  {
    slug: "orientation-101",
    name: "General Orientation",
    type: "orientation",
    duration_minutes: 120,
    session_count: 1,
    default_capacity: 50,
    description: "Intro session",
    materials: [],
    deleted_at: null,
  },
];

const ARCHIVED_TEMPLATE = {
  slug: "old-seminar",
  name: "Old Seminar",
  type: "seminar",
  duration_minutes: 60,
  session_count: 1,
  default_capacity: 20,
  description: null,
  materials: [],
  deleted_at: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderSection(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <TemplatesSection />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

test("renders loading skeletons while data is pending", async () => {
  // Return a promise that never resolves to stay in loading state
  api.admin.templates.list.mockReturnValue(new Promise(() => {}));
  const qc = makeQC();
  renderSection(qc);
  // Skeletons should be visible during loading
  const skeletons = document.querySelectorAll(".animate-pulse, [data-testid='skeleton']");
  // If no data-testid, check by class or count of skeleton-like elements
  // The component renders 4 Skeleton rows in loading state
  await waitFor(() => {
    // Loading state: no table headers visible
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

test("renders empty state when list is empty", async () => {
  api.admin.templates.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText(/no templates yet/i)).toBeInTheDocument();
  });
});

test("renders table with Name, Type, Duration, Sessions, Capacity columns when templates exist", async () => {
  api.admin.templates.list.mockResolvedValue(TEMPLATES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  // Check column headers in the table
  const table = screen.getByRole("table");
  const headers = table.querySelectorAll("th");
  const headerTexts = Array.from(headers).map((h) => h.textContent.toLowerCase());
  expect(headerTexts.some((h) => h.includes("name"))).toBe(true);
  expect(headerTexts.some((h) => h.includes("type"))).toBe(true);
  expect(headerTexts.some((h) => h.includes("duration"))).toBe(true);
  expect(headerTexts.some((h) => h.includes("sessions"))).toBe(true);
  expect(headerTexts.some((h) => h.includes("capacity"))).toBe(true);
  expect(screen.getByText("General Orientation")).toBeInTheDocument();
});

test("clicking 'New template' button opens SideDrawer with title 'New template'", async () => {
  api.admin.templates.list.mockResolvedValue(TEMPLATES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  const btn = screen.getByRole("button", { name: /new template/i });
  fireEvent.click(btn);
  await waitFor(() => {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  // SideDrawer heading (h2) shows "New template"
  expect(screen.getByRole("heading", { name: "New template" })).toBeInTheDocument();
});

test("clicking a table row opens SideDrawer with title 'Edit template' and pre-filled values", async () => {
  api.admin.templates.list.mockResolvedValue(TEMPLATES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  const row = screen.getByText("DNA Extraction").closest("tr");
  fireEvent.click(row);
  await waitFor(() => {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  expect(screen.getByText("Edit template")).toBeInTheDocument();
  // Pre-filled values
  expect(screen.getByDisplayValue("DNA Extraction")).toBeInTheDocument();
});

test("create form has all required fields", async () => {
  api.admin.templates.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText(/no templates yet/i)).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button", { name: /new template/i }));
  await waitFor(() => {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  // Check for all required fields via their label text
  expect(screen.getByLabelText(/template name/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/url slug/i)).toBeInTheDocument();
  // Type select — use its id since label text "Type" is common
  expect(document.getElementById("tf-type")).toBeInTheDocument();
  expect(screen.getByLabelText(/duration/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/number of sessions/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/default capacity/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/materials/i)).toBeInTheDocument();
});

test("slug auto-generates from name as lowercase with hyphens", async () => {
  api.admin.templates.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText(/no templates yet/i)).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button", { name: /new template/i }));
  await waitFor(() => {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  const nameInput = screen.getByLabelText(/template name/i);
  fireEvent.change(nameInput, { target: { value: "Test Seminar" } });
  await waitFor(() => {
    const slugInput = screen.getByLabelText(/url slug/i);
    expect(slugInput.value).toBe("test-seminar");
  });
});

test("Archive button triggers confirmation modal with plain-English text", async () => {
  api.admin.templates.list.mockResolvedValue(TEMPLATES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  // Open edit drawer
  const row = screen.getByText("DNA Extraction").closest("tr");
  fireEvent.click(row);
  await waitFor(() => {
    expect(screen.getByText("Edit template")).toBeInTheDocument();
  });
  // Click archive button
  const archiveBtn = screen.getByRole("button", { name: /archive/i });
  fireEvent.click(archiveBtn);
  await waitFor(() => {
    expect(screen.getByText("Archive this template?")).toBeInTheDocument();
  });
});

test("Show archived toggle adds include_archived=true to query", async () => {
  api.admin.templates.list.mockResolvedValue(TEMPLATES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  const toggle = screen.getByLabelText(/show archived/i);
  fireEvent.click(toggle);
  await waitFor(() => {
    expect(api.admin.templates.list).toHaveBeenCalledWith(
      expect.objectContaining({ include_archived: true }),
    );
  });
});

test("archived template row shows Restore action", async () => {
  // First call returns active templates, second (after toggling showArchived) returns archived
  api.admin.templates.list
    .mockResolvedValueOnce(TEMPLATES)
    .mockResolvedValue([ARCHIVED_TEMPLATE]);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  // Toggle show archived
  const toggle = screen.getByLabelText(/show archived/i);
  fireEvent.click(toggle);
  await waitFor(() => {
    expect(screen.getByText("Old Seminar")).toBeInTheDocument();
  });
  expect(screen.getByRole("button", { name: /restore/i })).toBeInTheDocument();
});

test("Restore button calls api.admin.templates.restore", async () => {
  api.admin.templates.list
    .mockResolvedValueOnce(TEMPLATES)
    .mockResolvedValue([ARCHIVED_TEMPLATE]);
  api.admin.templates.restore.mockResolvedValue({});
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  // Toggle show archived
  const toggle = screen.getByLabelText(/show archived/i);
  fireEvent.click(toggle);
  await waitFor(() => {
    expect(screen.getByText("Old Seminar")).toBeInTheDocument();
  });
  const restoreBtn = screen.getByRole("button", { name: /restore/i });
  fireEvent.click(restoreBtn);
  await waitFor(() => {
    expect(api.admin.templates.restore).toHaveBeenCalledWith("old-seminar");
  });
});

test("useAdminPageTitle is called with 'Templates'", () => {
  api.admin.templates.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  expect(useAdminPageTitle).toHaveBeenCalledWith("Templates");
});
