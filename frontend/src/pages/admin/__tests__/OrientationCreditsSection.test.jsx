// Issue #30 — OrientationCreditsSection: credit is permanent per
// (email, family); the quarter is "earned in" metadata only. The grant form
// still offers a quarter picker (defaulting to the one covering today, with
// an explicit "No quarter" choice), the table shows the earned-in quarter,
// and the list can be filtered by quarter.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const creditsListMock = vi.fn();
const creditsCreateMock = vi.fn();
const creditsRevokeMock = vi.fn();
const modulesListMock = vi.fn();
const quartersMock = vi.fn();

vi.mock("../../../lib/api", () => ({
  default: {
    admin: {
      modules: { list: (...a) => modulesListMock(...a) },
      orientationCredits: {
        list: (...a) => creditsListMock(...a),
        create: (...a) => creditsCreateMock(...a),
        revoke: (...a) => creditsRevokeMock(...a),
      },
    },
    public: {
      getQuarters: (...a) => quartersMock(...a),
    },
  },
}));

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

import OrientationCreditsSection from "../OrientationCreditsSection";

const iso = (d) => d.toISOString().slice(0, 10);
const NOW = new Date();

const CURRENT_Q = {
  id: "q-current",
  season: "summer",
  year: NOW.getFullYear(),
  label: "Session A",
  start_date: iso(new Date(NOW.getTime() - 20 * 86400000)),
  end_date: iso(new Date(NOW.getTime() + 20 * 86400000)),
  weeks_in_quarter: 6,
  display_name: "Summer Session A",
  archived_at: null,
};
const PAST_Q = {
  id: "q-past",
  season: "spring",
  year: NOW.getFullYear(),
  label: "",
  start_date: iso(new Date(NOW.getTime() - 200 * 86400000)),
  end_date: iso(new Date(NOW.getTime() - 120 * 86400000)),
  weeks_in_quarter: 11,
  display_name: "Spring (past)",
  archived_at: null,
};

const CREDIT = {
  id: "credit-1",
  volunteer_email: "vol@example.com",
  family_key: "intro-bio",
  quarter_id: "q-past",
  quarter_label: "Spring (past)",
  source: "grant",
  granted_by_user_id: "admin-1",
  granted_by_label: "Admin",
  granted_at: "2026-04-01T10:00:00Z",
  revoked_at: null,
  notes: null,
};

const MODULES = [
  { slug: "intro-bio", name: "Intro Bio", family_key: "intro-bio", deleted_at: null },
];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin/orientation-credits"]}>
        <OrientationCreditsSection />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  modulesListMock.mockResolvedValue(MODULES);
  quartersMock.mockResolvedValue([PAST_Q, CURRENT_Q]);
  creditsListMock.mockResolvedValue([CREDIT]);
});

describe("OrientationCreditsSection quarter metadata", () => {
  it("shows which quarter each credit was earned in", async () => {
    renderPage();
    expect(await screen.findByText("vol@example.com")).toBeInTheDocument();
    expect(screen.getByText("Quarter")).toBeInTheDocument();
    // The label shows in the table cell (it also appears as a filter option).
    expect(
      screen.getAllByText("Spring (past)").some((el) => el.tagName === "TD")
    ).toBe(true);
  });

  it("grant form defaults to the quarter covering today and sends quarter_id", async () => {
    creditsCreateMock.mockResolvedValue({ ...CREDIT, id: "credit-2" });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /grant credit/i }));

    const quarterSelect = await screen.findByLabelText("Quarter");
    await waitFor(() => expect(quarterSelect.value).toBe("q-current"));

    fireEvent.change(screen.getByLabelText(/volunteer email/i), {
      target: { value: "new@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/module family/i), {
      target: { value: "intro-bio" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^grant$/i }));

    await waitFor(() => expect(creditsCreateMock).toHaveBeenCalled());
    expect(creditsCreateMock.mock.calls[0][0]).toMatchObject({
      volunteer_email: "new@example.com",
      family_key: "intro-bio",
      quarter_id: "q-current",
    });
  });

  it("grants with quarter_id null when 'No quarter' is chosen", async () => {
    creditsCreateMock.mockResolvedValue({
      ...CREDIT,
      id: "credit-3",
      quarter_id: null,
      quarter_label: null,
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /grant credit/i }));

    const quarterSelect = await screen.findByLabelText("Quarter");
    await waitFor(() => expect(quarterSelect.value).toBe("q-current"));
    fireEvent.change(quarterSelect, { target: { value: "none" } });

    fireEvent.change(screen.getByLabelText(/volunteer email/i), {
      target: { value: "old-timer@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/module family/i), {
      target: { value: "intro-bio" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^grant$/i }));

    await waitFor(() => expect(creditsCreateMock).toHaveBeenCalled());
    expect(creditsCreateMock.mock.calls[0][0]).toMatchObject({
      volunteer_email: "old-timer@example.com",
      family_key: "intro-bio",
      quarter_id: null,
    });
  });

  it("grants with quarter_id null when no quarter covers today", async () => {
    quartersMock.mockResolvedValue([PAST_Q]);
    creditsCreateMock.mockResolvedValue({
      ...CREDIT,
      id: "credit-4",
      quarter_id: null,
      quarter_label: null,
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /grant credit/i }));

    fireEvent.change(screen.getByLabelText(/volunteer email/i), {
      target: { value: "new@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/module family/i), {
      target: { value: "intro-bio" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^grant$/i }));

    // No "quarter is required" validation error — quarter is optional metadata.
    await waitFor(() => expect(creditsCreateMock).toHaveBeenCalled());
    expect(creditsCreateMock.mock.calls[0][0]).toMatchObject({
      volunteer_email: "new@example.com",
      family_key: "intro-bio",
      quarter_id: null,
    });
  });

  it("filters the list by quarter", async () => {
    renderPage();
    await screen.findByText("vol@example.com");

    fireEvent.change(screen.getByLabelText(/filter by quarter/i), {
      target: { value: "q-past" },
    });

    await waitFor(() => {
      const calls = creditsListMock.mock.calls;
      expect(calls[calls.length - 1][0]).toMatchObject({ quarter_id: "q-past" });
    });
  });
});
