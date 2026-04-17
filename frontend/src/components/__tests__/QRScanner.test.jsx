// Phase 28 — QRScanner tests. @zxing/browser is mocked to avoid camera
// access in JSDOM. The tests focus on the three paths we own:
//   - Component renders open-state content.
//   - extractManageToken correctly parses URLs and bare tokens.
//   - Text-input fallback submission calls lookup + check-in.
//   - "Already checked in" path skips the check-in POST.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock @zxing/browser so decodeFromVideoDevice never actually opens a camera.
vi.mock("@zxing/browser", () => {
  class BrowserMultiFormatReader {
    async decodeFromVideoDevice() {
      // No-op — the tests drive scanning via the manual fallback form.
      return;
    }
    reset() {}
  }
  return { BrowserMultiFormatReader };
});

vi.mock("../../lib/api", () => {
  const lookupByManageToken = vi.fn();
  const checkInSignup = vi.fn();
  const api = {
    organizer: {
      lookupByManageToken,
      checkInSignup,
    },
  };
  return { api, default: api };
});

vi.mock("../../state/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { api } from "../../lib/api";
import { toast } from "../../state/toast";
import QRScanner, {
  extractManageToken,
} from "../organizer/QRScanner";

describe("extractManageToken", () => {
  it("parses manage_token from a full URL", () => {
    const url =
      "https://scitrek.example.com/manage?manage_token=abcd1234efgh5678";
    expect(extractManageToken(url)).toBe("abcd1234efgh5678");
  });

  it("falls back to `token` param when manage_token is absent", () => {
    const url = "https://scitrek.example.com/signup/manage?token=zzzz9999yyyy";
    expect(extractManageToken(url)).toBe("zzzz9999yyyy");
  });

  it("accepts a bare token with no URL structure", () => {
    const bare = "justaraw_tokenvalue_0123";
    expect(extractManageToken(bare)).toBe(bare);
  });

  it("returns null for garbage input", () => {
    expect(extractManageToken("")).toBe(null);
    expect(extractManageToken("hello world")).toBe(null);
  });
});

describe("QRScanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders when open", () => {
    render(<QRScanner open onClose={() => {}} />);
    expect(
      screen.getByRole("heading", { name: /scan qr to check in/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("qr-fallback-form")).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    const { container } = render(<QRScanner open={false} />);
    expect(container.innerHTML).toBe("");
  });

  it("fallback submit calls lookup and then checkIn, shows success toast", async () => {
    api.organizer.lookupByManageToken.mockResolvedValueOnce({
      signup_id: "sid-123",
      status: "confirmed",
      volunteer_first_name: "Ada",
      volunteer_last_name: "Lovelace",
      volunteer_email: "ada@example.com",
      event_id: "evt-1",
    });
    api.organizer.checkInSignup.mockResolvedValueOnce({});

    const user = userEvent.setup();
    render(<QRScanner open onClose={() => {}} />);

    const input = screen.getByLabelText(/magic link or manage token/i);
    await user.type(input, "https://x/manage?manage_token=abc123xyz9876543");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() =>
      expect(api.organizer.lookupByManageToken).toHaveBeenCalledWith(
        "abc123xyz9876543",
      ),
    );
    await waitFor(() =>
      expect(api.organizer.checkInSignup).toHaveBeenCalledWith("sid-123"),
    );
    expect(toast.success).toHaveBeenCalledWith(
      expect.stringMatching(/Checked in Ada Lovelace/),
    );
  });

  it("skips check-in POST when lookup reports already checked_in", async () => {
    api.organizer.lookupByManageToken.mockResolvedValueOnce({
      signup_id: "sid-456",
      status: "checked_in",
      volunteer_first_name: "Grace",
      volunteer_last_name: "Hopper",
      volunteer_email: "grace@example.com",
      event_id: "evt-2",
    });

    const user = userEvent.setup();
    render(<QRScanner open onClose={() => {}} />);

    const input = screen.getByLabelText(/magic link or manage token/i);
    await user.type(input, "bareTokenOfAtLeastSixteenChars");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() =>
      expect(api.organizer.lookupByManageToken).toHaveBeenCalled(),
    );
    expect(api.organizer.checkInSignup).not.toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalledWith(
      expect.stringMatching(/already checked in/i),
    );
  });

  it("shows error toast on unrecognized QR", async () => {
    const user = userEvent.setup();
    render(<QRScanner open onClose={() => {}} />);

    const input = screen.getByLabelText(/magic link or manage token/i);
    await user.type(input, "short");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(toast.error).toHaveBeenCalledWith(
      expect.stringMatching(/unrecognized/i),
    );
    expect(api.organizer.lookupByManageToken).not.toHaveBeenCalled();
  });
});
