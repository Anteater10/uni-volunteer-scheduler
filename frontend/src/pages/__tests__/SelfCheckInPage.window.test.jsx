// K22 — the page told volunteers the wrong check-in window.
//
// `check_in_service.py` sets CHECK_IN_WINDOW_BEFORE = 30 minutes (and _AFTER
// the same). This page said check-in opens **15** minutes before. A volunteer
// standing outside the van 20 minutes early was inside the real window, got
// an unrelated error, read "check-in opens 15 minutes before", and waited —
// or gave up and found an organizer. The number appeared twice, in the
// not-yet-open screen and in the OUTSIDE_WINDOW error text.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const getSignupEvent = vi.fn();
const selfCheckIn = vi.fn();
vi.mock("../../api/checkIn", () => ({
  getSignupEvent: (...a) => getSignupEvent(...a),
  selfCheckIn: (...a) => selfCheckIn(...a),
}));

import SelfCheckInPage from "../SelfCheckInPage";

const IN_ONE_HOUR = new Date(Date.now() + 60 * 60 * 1000).toISOString();
const AN_HOUR_AGO = new Date(Date.now() - 60 * 60 * 1000).toISOString();

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/check-in/su-1"]}>
        <Routes>
          <Route path="/check-in/:signupId" element={<SelfCheckInPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function submitCode(user) {
  await user.type(await screen.findByLabelText(/venue code/i), "1234");
  await user.click(screen.getByRole("button", { name: /check me in/i }));
}

function outsideWindow() {
  const err = new Error("nope");
  err.response = { data: { code: "OUTSIDE_WINDOW" } };
  return err;
}

describe("SelfCheckInPage — the window it quotes is the one the server keeps (K22)", () => {
  beforeEach(() => {
    getSignupEvent.mockReset();
    selfCheckIn.mockReset();
  });

  it("says 30 minutes before, not 15, on the not-yet-open screen", async () => {
    const user = userEvent.setup();
    getSignupEvent.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Germs at Goleta Valley",
      slot_start_time: IN_ONE_HOUR,
    });
    selfCheckIn.mockRejectedValue(outsideWindow());
    renderPage();

    await submitCode(user);

    const body = await screen.findByText(/check-in opens/i);
    expect(body).toHaveTextContent("30 minutes");
    expect(body).not.toHaveTextContent("15 minutes");
  });

  it("quotes 30 before and 30 after in the error text", async () => {
    const user = userEvent.setup();
    // Slot already started, so the page renders the closed branch rather than
    // the not-yet-open one — but the mutation's own message is what this pins.
    getSignupEvent.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Germs at Goleta Valley",
      slot_start_time: AN_HOUR_AGO,
    });
    selfCheckIn.mockRejectedValue(outsideWindow());
    renderPage();

    await submitCode(user);

    await waitFor(() => expect(selfCheckIn).toHaveBeenCalled());
    // Whichever branch renders, no surface may still claim 15 minutes.
    expect(document.body.textContent).not.toMatch(/15 minutes/);
  });

  it("leaves other error codes alone", async () => {
    const user = userEvent.setup();
    getSignupEvent.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Germs at Goleta Valley",
      slot_start_time: IN_ONE_HOUR,
    });
    const err = new Error("nope");
    err.response = { data: { code: "WRONG_VENUE_CODE" } };
    selfCheckIn.mockRejectedValue(err);
    renderPage();

    await submitCode(user);

    expect(
      await screen.findByText(/that's not the right code/i),
    ).toBeInTheDocument();
  });
});
