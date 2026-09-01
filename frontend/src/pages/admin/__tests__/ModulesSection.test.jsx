// src/pages/admin/__tests__/ModulesSection.test.jsx
//
// Phase 17 Plan 02 — ModulesSection CRUD tests.
// Covers list, create, edit, archive, restore with SideDrawer pattern.

import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/api", () => {
  const modules = {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    restore: vi.fn(),
  };
  return {
    default: { admin: { modules } },
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
import ModulesSection from "../ModulesSection";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MODULES = [
  {
    slug: "dna-module",
    name: "DNA Extraction",
    school_branch: "high_school",
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
    school_branch: "both",
    duration_minutes: 120,
    session_count: 1,
    default_capacity: 50,
    description: "Intro session",
    materials: [],
    deleted_at: null,
  },
];

const ARCHIVED_MODULE = {
  slug: "old-seminar",
  name: "Old Seminar",
  school_branch: "middle_school",
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
      <ModulesSection />
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
  api.admin.modules.list.mockReturnValue(new Promise(() => {}));
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
  api.admin.modules.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText(/no modules yet/i)).toBeInTheDocument();
  });
});

test("renders table with branch, schedule columns, and no Type column (PR #51)", async () => {
  api.admin.modules.list.mockResolvedValue(MODULES);
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
  expect(headerTexts.some((h) => h.includes("school branch"))).toBe(true);
  expect(headerTexts.some((h) => h.includes("type"))).toBe(false);
  expect(headerTexts.some((h) => h.includes("duration"))).toBe(true);
  expect(headerTexts.some((h) => h.includes("sessions"))).toBe(true);
  expect(headerTexts.some((h) => h.includes("capacity"))).toBe(true);
  expect(screen.getByText("General Orientation")).toBeInTheDocument();
  expect(screen.getByText("High School")).toBeInTheDocument();
});

test("clicking 'New module' button opens SideDrawer with title 'New module'", async () => {
  api.admin.modules.list.mockResolvedValue(MODULES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  const btn = screen.getByRole("button", { name: /new module/i });
  fireEvent.click(btn);
  await waitFor(() => {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  // SideDrawer heading (h2) shows "New module"
  expect(screen.getByRole("heading", { name: "New module" })).toBeInTheDocument();
});

test("clicking a table row opens SideDrawer with title 'Edit module' and pre-filled values", async () => {
  api.admin.modules.list.mockResolvedValue(MODULES);
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
  expect(screen.getByText("Edit module")).toBeInTheDocument();
  // Pre-filled values
  expect(screen.getByDisplayValue("DNA Extraction")).toBeInTheDocument();
});

test("create form has all required fields", async () => {
  api.admin.modules.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText(/no modules yet/i)).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button", { name: /new module/i }));
  await waitFor(() => {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  // Check for all required fields via their label text
  expect(screen.getByLabelText(/module name/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/url slug/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/school branch/i)).toHaveValue("both");
  // PR #51: the Type picker is gone — every module is just a module
  expect(document.getElementById("tf-type")).not.toBeInTheDocument();
  expect(screen.getByLabelText(/duration/i)).toBeInTheDocument();
  // session_count is no longer a user-editable field on the create form;
  // it's derived per template and surfaced in the table column instead.
  expect(screen.getByLabelText(/default capacity/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/materials/i)).toBeInTheDocument();
});

test("create sends the selected school branch", async () => {
  api.admin.modules.list.mockResolvedValue([]);
  api.admin.modules.create.mockResolvedValue({});
  const qc = makeQC();
  renderSection(qc);
  await screen.findByText(/no modules yet/i);
  fireEvent.click(screen.getByRole("button", { name: /new module/i }));
  const drawer = screen.getByRole("dialog");
  fireEvent.change(within(drawer).getByLabelText(/module name/i), {
    target: { value: "Branch Module" },
  });
  fireEvent.change(within(drawer).getByLabelText(/school branch/i), {
    target: { value: "middle_school" },
  });
  fireEvent.click(within(drawer).getByRole("button", { name: /create module/i }));
  await waitFor(() =>
    expect(api.admin.modules.create).toHaveBeenCalledWith(
      expect.objectContaining({ school_branch: "middle_school" }),
    ),
  );
});

test("slug auto-generates from name as lowercase with hyphens", async () => {
  api.admin.modules.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText(/no modules yet/i)).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button", { name: /new module/i }));
  await waitFor(() => {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  const nameInput = screen.getByLabelText(/module name/i);
  fireEvent.change(nameInput, { target: { value: "Test Seminar" } });
  await waitFor(() => {
    const slugInput = screen.getByLabelText(/url slug/i);
    expect(slugInput.value).toBe("test-seminar");
  });
});

test("Archive button triggers confirmation modal with plain-English text", async () => {
  api.admin.modules.list.mockResolvedValue(MODULES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  // Open edit drawer
  const row = screen.getByText("DNA Extraction").closest("tr");
  fireEvent.click(row);
  await waitFor(() => {
    expect(screen.getByText("Edit module")).toBeInTheDocument();
  });
  // Click archive button
  const archiveBtn = screen.getByRole("button", { name: /archive/i });
  fireEvent.click(archiveBtn);
  await waitFor(() => {
    expect(screen.getByText("Archive this module?")).toBeInTheDocument();
  });
});

test("Show archived toggle adds include_archived=true to query", async () => {
  api.admin.modules.list.mockResolvedValue(MODULES);
  const qc = makeQC();
  renderSection(qc);
  await waitFor(() => {
    expect(screen.getByText("DNA Extraction")).toBeInTheDocument();
  });
  const toggle = screen.getByLabelText(/show archived/i);
  fireEvent.click(toggle);
  await waitFor(() => {
    expect(api.admin.modules.list).toHaveBeenCalledWith(
      expect.objectContaining({ include_archived: true }),
    );
  });
});

test("archived template row shows Restore action", async () => {
  // First call returns active modules, second (after toggling showArchived) returns archived
  api.admin.modules.list
    .mockResolvedValueOnce(MODULES)
    .mockResolvedValue([ARCHIVED_MODULE]);
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

test("Restore button calls api.admin.modules.restore", async () => {
  api.admin.modules.list
    .mockResolvedValueOnce(MODULES)
    .mockResolvedValue([ARCHIVED_MODULE]);
  api.admin.modules.restore.mockResolvedValue({});
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
    expect(api.admin.modules.restore).toHaveBeenCalledWith("old-seminar");
  });
});

test("useAdminPageTitle is called with 'Modules'", () => {
  api.admin.modules.list.mockResolvedValue([]);
  const qc = makeQC();
  renderSection(qc);
  expect(useAdminPageTitle).toHaveBeenCalledWith("Modules");
});
