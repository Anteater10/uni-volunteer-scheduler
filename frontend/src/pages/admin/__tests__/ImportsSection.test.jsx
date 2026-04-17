// src/pages/admin/__tests__/ImportsSection.test.jsx
//
// Phase 18 Plan 02 — ImportsSection frontend tests.
// Covers: explainer text, empty state, import list, preview rows, commit gating,
// error humanization, and processing indicator.

import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/api", () => {
  const imports = {
    list: vi.fn(),
    get: vi.fn(),
    upload: vi.fn(),
    commit: vi.fn(),
    retry: vi.fn(),
    updateRow: vi.fn(),
    revalidate: vi.fn().mockResolvedValue({}),
  };
  return {
    default: { admin: { imports } },
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
import ImportsSection from "../ImportsSection";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const IMPORT_READY = {
  id: "imp-001",
  filename: "spring2026.csv",
  status: "ready",
  error_message: null,
  created_at: new Date().toISOString(),
  result_payload: {
    raw_csv: "...",
    rows: [
      {
        index: 0,
        status: "ok",
        normalized: {
          module_slug: "dna-extraction",
          start_at: "2026-05-15T14:00:00Z",
          location: "Broida 1015",
          capacity: 30,
        },
        warnings: [],
        original: {},
      },
      {
        index: 1,
        status: "low_confidence",
        normalized: {
          module_slug: "mystery-module",
          start_at: "2026-05-22T10:00:00Z",
          location: "Unknown Room",
          capacity: 25,
        },
        warnings: ["Module slug not recognized"],
        original: {},
      },
      {
        index: 2,
        status: "conflict",
        normalized: {
          module_slug: "dna-extraction",
          start_at: "2026-05-15T14:00:00Z",
          location: "Broida 1015",
          capacity: 30,
        },
        warnings: ["Overlaps with existing event"],
        original: {},
      },
    ],
    summary: {
      to_create: 1,
      to_review: 1,
      conflicts: 1,
      total: 3,
    },
  },
};

const IMPORT_FAILED = {
  id: "imp-002",
  filename: "bad-upload.csv",
  status: "failed",
  error_message: "AuthenticationError: Incorrect API key provided",
  created_at: new Date().toISOString(),
  result_payload: null,
};

const IMPORT_PROCESSING = {
  id: "imp-003",
  filename: "processing.csv",
  status: "processing",
  error_message: null,
  created_at: new Date().toISOString(),
  result_payload: null,
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
    <QueryClientProvider client={qc || makeQC()}>
      <ImportsSection />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ImportsSection", () => {
  it("renders explainer text", async () => {
    api.admin.imports.list.mockResolvedValue([]);
    renderSection();
    await waitFor(() => {
      expect(screen.getByText(/Upload a quarterly/i)).toBeInTheDocument();
    });
  });

  it("shows empty state when no imports", async () => {
    api.admin.imports.list.mockResolvedValue([]);
    renderSection();
    await waitFor(() => {
      expect(screen.getByText(/No imports/i)).toBeInTheDocument();
    });
  });

  it("renders import list with status chips", async () => {
    api.admin.imports.list.mockResolvedValue([IMPORT_READY, IMPORT_FAILED]);
    renderSection();
    await waitFor(() => {
      expect(screen.getByText("spring2026.csv")).toBeInTheDocument();
      expect(screen.getByText("bad-upload.csv")).toBeInTheDocument();
    });
    // Status chips should appear
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows preview rows with correct styling when import row is clicked", async () => {
    api.admin.imports.list.mockResolvedValue([IMPORT_READY]);
    renderSection();

    // Wait for the import filename to appear
    await waitFor(() => {
      expect(screen.getByText("spring2026.csv")).toBeInTheDocument();
    });

    // Click the import row to expand the detail panel
    fireEvent.click(screen.getByText("spring2026.csv"));

    await waitFor(() => {
      // Summary banner text should appear
      expect(screen.getByText(/ready to create/i)).toBeInTheDocument();
    });

    // Check row status chips
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Needs Review")).toBeInTheDocument();
    expect(screen.getByText("Conflict")).toBeInTheDocument();

    // Check row background classes exist in the DOM
    const table = document.querySelector("table:last-of-type");
    expect(table).not.toBeNull();

    // Yellow row for low_confidence
    const yellowRow = document.querySelector(".bg-yellow-50");
    expect(yellowRow).not.toBeNull();

    // Red row for conflict
    const redRow = document.querySelector(".bg-red-50");
    expect(redRow).not.toBeNull();
  });

  it("commit button is disabled when low_confidence rows exist", async () => {
    api.admin.imports.list.mockResolvedValue([IMPORT_READY]);
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("spring2026.csv")).toBeInTheDocument();
    });

    // Click to expand detail panel
    fireEvent.click(screen.getByText("spring2026.csv"));

    await waitFor(() => {
      expect(screen.getByText(/Resolve all flagged rows first/i)).toBeInTheDocument();
    });

    const commitButton = screen.getByText(/Resolve all flagged rows first/i).closest("button");
    expect(commitButton).toHaveAttribute("disabled");
  });

  it("humanizes error messages — no raw error class names shown", async () => {
    api.admin.imports.list.mockResolvedValue([IMPORT_FAILED]);
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("bad-upload.csv")).toBeInTheDocument();
    });

    // Raw error text "AuthenticationError" should NOT appear
    expect(screen.queryByText(/AuthenticationError/)).not.toBeInTheDocument();

    // But user-friendly message SHOULD appear
    expect(screen.getByText(/API key/i)).toBeInTheDocument();
  });

  it("shows processing indicator for a processing import when clicked", async () => {
    api.admin.imports.list.mockResolvedValue([IMPORT_PROCESSING]);
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("processing.csv")).toBeInTheDocument();
    });

    // Click to expand detail panel
    fireEvent.click(screen.getByText("processing.csv"));

    await waitFor(() => {
      expect(screen.getByText(/Processing your CSV/i)).toBeInTheDocument();
    });
  });

  it("renders Re-run button only for failed imports", async () => {
    api.admin.imports.list.mockResolvedValue([IMPORT_READY, IMPORT_FAILED]);
    renderSection();

    await waitFor(() => {
      expect(screen.getByText("spring2026.csv")).toBeInTheDocument();
    });

    // Only one Re-run button (for the failed import)
    const rerunButtons = screen.getAllByText("Re-run");
    expect(rerunButtons).toHaveLength(1);
  });
});
