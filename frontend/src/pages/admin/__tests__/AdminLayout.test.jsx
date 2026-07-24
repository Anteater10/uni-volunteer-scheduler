import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminLayout from "../AdminLayout";

// Mock useAuth so the layout renders without a real AuthProvider.
vi.mock("../../../state/useAuth", () => ({
  useAuth: () => ({
    user: { name: "Andy", email: "andy@example.com", role: "admin" },
    logout: vi.fn(),
  }),
}));

// Issue #24: the layout queries the entered quarters for the setup guard.
// A quarter covering "today" keeps the guard quiet in these layout tests.
vi.mock("../../../lib/api", () => {
  const apiMock = {
    public: {
      getQuarters: vi.fn(async () => {
        const today = new Date();
        const iso = (d) => d.toISOString().slice(0, 10);
        return [
          {
            id: "q-now",
            season: "fall",
            year: today.getFullYear(),
            label: "",
            start_date: iso(new Date(today.getTime() - 30 * 86400000)),
            end_date: iso(new Date(today.getTime() + 40 * 86400000)),
            weeks_in_quarter: 11,
            display_name: "Current quarter",
            archived_at: null,
          },
        ];
      }),
    },
    // The layout now reads site settings to decide whether the Audit Logs
    // nav item is shown. Default the flag off for these tests.
    admin: {
      siteSettings: {
        get: vi.fn(async () => ({ show_audit_logs_tab: false })),
      },
    },
  };
  // AdminLayout imports the named `api` export; older call sites use default.
  return { default: apiMock, api: apiMock };
});

function renderAtDesktop(width = 1200) {
  Object.defineProperty(window, "innerWidth", {
    writable: true,
    configurable: true,
    value: width,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<div data-testid="child-outlet">OUTLET CONTENT</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AdminLayout", () => {
  it("renders the expected sidebar nav items (no Overrides, no Portals)", () => {
    renderAtDesktop();
    for (const label of [
      "Overview",
      "Events",
      "Operations",
      "Templates",
      "Imports",
      "Users",
      "Exports",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: /overrides/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /portals/i })).toBeNull();
    // Audit Logs is gated behind the show_audit_logs_tab site setting, which
    // the mock returns false — so it must not appear by default.
    expect(screen.queryByRole("link", { name: /audit logs/i })).toBeNull();
  });

  it("hides the Copilot feedback nav item when the copilot flag is off", () => {
    // Same gate as CopilotFab: the analytics page for an invisible feature
    // must not be reachable from the nav. Stub the env explicitly so the
    // test doesn't depend on the developer's local .env value.
    vi.stubEnv("VITE_COPILOT_ENABLED", "false");
    try {
      renderAtDesktop();
      expect(
        screen.queryByRole("link", { name: /copilot feedback/i })
      ).toBeNull();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("shows the Copilot feedback nav item when VITE_COPILOT_ENABLED=true", () => {
    vi.stubEnv("VITE_COPILOT_ENABLED", "true");
    try {
      renderAtDesktop();
      expect(
        screen.getByRole("link", { name: /copilot feedback/i })
      ).toBeInTheDocument();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("renders the child outlet when window width >= 768px", () => {
    renderAtDesktop(1200);
    expect(screen.getByTestId("child-outlet")).toBeInTheDocument();
    expect(
      screen.queryByText(
        /This admin view is designed for screens ≥ 768px/i,
      ),
    ).toBeNull();
  });

  it("renders DesktopOnlyBanner when window width < 768px", () => {
    renderAtDesktop(500);
    expect(
      screen.getByText(/This admin view is designed for screens ≥ 768px/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("child-outlet")).toBeNull();
  });
});
