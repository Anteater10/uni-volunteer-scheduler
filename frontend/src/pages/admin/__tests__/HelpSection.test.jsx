// The Help page is two different pages: admins see every card, organizers
// only the ones for screens they can reach. The close-out card must describe
// closing as undoable (2026-10-13, Kim's report) — it used to read as final.
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const authState = vi.hoisted(() => ({ user: null }));

vi.mock("../AdminLayout", () => ({ useAdminPageTitle: vi.fn() }));
vi.mock("../../../state/useAuth", () => ({
  useAuth: () => ({ user: authState.user }),
}));

import HelpSection from "../HelpSection";

describe("HelpSection", () => {
  it("shows admins every card, including admin-only ones", () => {
    authState.user = { role: "admin" };
    render(<HelpSection />);
    expect(screen.getByText("Admin Help")).toBeInTheDocument();
    expect(screen.getByText("How to invite a new user")).toBeInTheDocument();
  });

  it("hides admin-only cards from organizers (and from a missing user)", () => {
    for (const user of [{ role: "organizer" }, null]) {
      authState.user = user;
      const { unmount } = render(<HelpSection />);
      expect(screen.getByText("Organizer Help")).toBeInTheDocument();
      expect(screen.queryByText("How to invite a new user")).not.toBeInTheDocument();
      expect(screen.getByText("How to check volunteers in on the day")).toBeInTheDocument();
      unmount();
    }
  });

  it("says closing a session can be undone and spares future sessions", () => {
    authState.user = { role: "organizer" };
    render(<HelpSection />);
    const body = screen.getByText(/On the live roster, click 'End slot'/);
    expect(body).toHaveTextContent(/Reopen slot/);
    expect(body).toHaveTextContent(/nothing is final/i);
    expect(body).toHaveTextContent(/already started/);
  });
});
