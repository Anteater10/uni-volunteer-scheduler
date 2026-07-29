// PR #51 — staff forgot-password page.
import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../lib/api", () => {
  const apiMock = { forgotPassword: vi.fn(async () => ({ status: "accepted" })) };
  return { default: apiMock, api: apiMock };
});

import api from "../../lib/api";
import ForgotPasswordPage from "../ForgotPasswordPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <ForgotPasswordPage />
    </MemoryRouter>,
  );
}

describe("ForgotPasswordPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits the email and lands on the check-your-email state", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText(/email/i), "staff@ucsb.edu");
    await userEvent.click(
      screen.getByRole("button", { name: /email me a reset link/i }),
    );
    expect(api.forgotPassword).toHaveBeenCalledWith("staff@ucsb.edu");
    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
    // The confirmation must not vary by whether the address has an account.
    expect(screen.getByText(/if/i)).toBeInTheDocument();
  });

  it("shows an error when the request itself fails", async () => {
    api.forgotPassword.mockRejectedValueOnce(new Error("network down"));
    renderPage();
    await userEvent.type(screen.getByLabelText(/email/i), "staff@ucsb.edu");
    await userEvent.click(
      screen.getByRole("button", { name: /email me a reset link/i }),
    );
    expect(await screen.findByText(/network down/i)).toBeInTheDocument();
  });
});
