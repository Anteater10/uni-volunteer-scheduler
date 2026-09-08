// src/components/admin/__tests__/SignupQRModal.test.jsx
//
// SCRUM-13 (P6) — the signup QR encodes the PUBLIC signup URL and carries no
// credential, unlike the check-in QR. The one real trap is visibility:
// backend/app/routers/public/events.py:79 allow-lists exactly "public", so a
// code printed for a private or draft event scans to a 404. The modal must
// refuse to render one.

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { toast } from "../../../state/toast";
import SignupQRModal from "../SignupQRModal";

function renderModal(props = {}) {
  return render(
    <SignupQRModal
      open
      onClose={() => {}}
      eventId="evt-1"
      eventTitle="Bio @ Lincoln"
      visibility="public"
      {...props}
    />,
  );
}

describe("SignupQRModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no canvas backend; QRCodeCanvas only needs getContext to not
    // throw. The PNG bytes are not what these tests are about.
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
      fillRect: vi.fn(),
      clearRect: vi.fn(),
      createImageData: vi.fn(() => ({ data: [] })),
      putImageData: vi.fn(),
      drawImage: vi.fn(),
      scale: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      translate: vi.fn(),
    }));
  });

  it("encodes the public signup URL, not the check-in URL", () => {
    renderModal();

    const link = screen.getByRole("link", { name: /volunteer\/events/i });
    expect(link).toHaveAttribute(
      "href",
      expect.stringContaining("/volunteer/events/evt-1"),
    );
    expect(link.getAttribute("href")).not.toContain("event-check-in");
    expect(link.getAttribute("href")).not.toContain("?v=");
  });

  it("names the event above the code", () => {
    renderModal();
    expect(screen.getByText("Bio @ Lincoln")).toBeInTheDocument();
  });

  it("refuses to render a code for a non-public event", () => {
    renderModal({ visibility: "private" });

    expect(screen.getByText(/isn't public/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /volunteer\/events/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /download png/i }),
    ).not.toBeInTheDocument();
  });

  it("treats a missing visibility as not public (the column is nullable)", () => {
    renderModal({ visibility: undefined });
    expect(screen.getByText(/isn't public/i)).toBeInTheDocument();
  });

  it("copies the signup link to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderModal();
    await userEvent.click(screen.getByRole("button", { name: /copy link/i }));

    expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining("/volunteer/events/evt-1"),
    );
    expect(toast.success).toHaveBeenCalled();
  });

  it("downloads the code as a PNG named after the event", async () => {
    const clickSpy = vi.fn();
    const origCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = origCreate(tag);
      if (tag === "a") el.click = clickSpy;
      return el;
    });
    HTMLCanvasElement.prototype.toDataURL = vi.fn(() => "data:image/png;base64,x");

    renderModal();
    await userEvent.click(
      screen.getByRole("button", { name: /download png/i }),
    );

    expect(clickSpy).toHaveBeenCalled();
    document.createElement.mockRestore();
  });

  it("renders nothing when closed", () => {
    const { container } = renderModal({ open: false });
    expect(container).toBeEmptyDOMElement();
  });
});
