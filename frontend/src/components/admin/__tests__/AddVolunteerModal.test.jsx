// AddVolunteerModal.test.jsx — staff add a volunteer to an event by hand.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../../lib/api", () => {
  const apiMock = { admin: { addVolunteer: vi.fn() } };
  return { api: apiMock, default: apiMock };
});
vi.mock("../../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { api } from "../../../lib/api";
import { toast } from "../../../state/toast";
import AddVolunteerModal from "../AddVolunteerModal";

const EVENT = {
  shifts: [
    {
      id: "sh-1",
      name: "Tue P1",
      capacity: 5,
      current_count: 1,
      sessions: [{ start_time: "2026-10-27T16:00:00Z" }],
    },
    { id: "sh-2", name: "Wed P2", capacity: 1, current_count: 1, sessions: [] },
  ],
  slots: [
    {
      id: "or-1",
      slot_type: "orientation",
      start_time: "2026-10-26T18:00:00Z",
      capacity: 10,
      current_count: 2,
    },
    { id: "p-1", slot_type: "period", start_time: "2026-10-27T16:00:00Z" },
  ],
};

function renderModal(props = {}) {
  const onClose = vi.fn();
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <AddVolunteerModal open onClose={onClose} eventId="evt-1" event={EVENT} {...props} />
    </QueryClientProvider>,
  );
  return { onClose };
}

async function fillIdentity() {
  await userEvent.type(screen.getByLabelText(/first name/i), "Maya");
  await userEvent.type(screen.getByLabelText(/last name/i), "Lopez");
  await userEvent.type(screen.getByLabelText(/^email$/i), "maya@example.com");
}

describe("AddVolunteerModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists shifts and only orientation sessions, flagging full ones", () => {
    renderModal();
    expect(screen.getByText("Tue P1")).toBeInTheDocument();
    expect(screen.getByText("Wed P2")).toBeInTheDocument();
    expect(screen.getAllByText("Orientation")).toHaveLength(1);
    expect(screen.getAllByText("Full")).toHaveLength(1);
  });

  it("shows empty notes when the event has no shifts or orientations", () => {
    renderModal({ event: undefined });
    expect(screen.getByText(/no shifts on this event/i)).toBeInTheDocument();
    expect(screen.getByText(/no orientation sessions on this event/i)).toBeInTheDocument();
  });

  it("requires name and email", async () => {
    renderModal();
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    expect(screen.getByText(/first name, last name and email are required/i)).toBeInTheDocument();
    expect(api.admin.addVolunteer).not.toHaveBeenCalled();
  });

  it("requires at least one shift or orientation", async () => {
    renderModal();
    await fillIdentity();
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    expect(screen.getByText(/pick at least one shift/i)).toBeInTheDocument();
    expect(api.admin.addVolunteer).not.toHaveBeenCalled();
  });

  it("submits the selection and closes", async () => {
    api.admin.addVolunteer.mockResolvedValue({
      volunteer_id: "v-1",
      bookings: [{ status: "confirmed" }],
    });
    const { onClose } = renderModal();
    await fillIdentity();
    await userEvent.type(screen.getByLabelText(/phone/i), "805-555-1234");
    const [shiftBox, fullShiftBox, orientBox] = screen.getAllByRole("checkbox");
    await userEvent.click(shiftBox);
    await userEvent.click(fullShiftBox);
    await userEvent.click(fullShiftBox); // untoggle
    await userEvent.click(orientBox);
    await userEvent.click(screen.getByLabelText(/seat them anyway/i));
    await userEvent.click(screen.getByLabelText(/send them a confirmation email/i));
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.admin.addVolunteer).toHaveBeenCalledWith("evt-1", {
      first_name: "Maya",
      last_name: "Lopez",
      email: "maya@example.com",
      phone: "805-555-1234",
      shift_ids: ["sh-1"],
      slot_ids: ["or-1"],
      allow_overfill: true,
      send_email: false,
    });
    expect(toast.success).toHaveBeenCalledWith("Volunteer added.");
  });

  it("sends a null phone and says when someone was waitlisted", async () => {
    api.admin.addVolunteer.mockResolvedValue({
      volunteer_id: "v-1",
      bookings: [{ status: "waitlisted" }],
    });
    renderModal();
    await fillIdentity();
    await userEvent.click(screen.getAllByRole("checkbox")[1]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(api.admin.addVolunteer.mock.calls[0][1].phone).toBeNull();
    expect(toast.success.mock.calls[0][0]).toMatch(/1 on the waitlist/);
  });

  it("shows the server's error and stays open", async () => {
    api.admin.addVolunteer.mockRejectedValue(
      new Error("maya@example.com is already on this shift."),
    );
    const { onClose } = renderModal();
    await fillIdentity();
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));

    expect(await screen.findByText(/already on this shift/i)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("falls back to a generic error message", async () => {
    api.admin.addVolunteer.mockRejectedValue({});
    renderModal();
    await fillIdentity();
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    expect(await screen.findByText(/couldn't add the volunteer/i)).toBeInTheDocument();
  });

  it("copes with sparse data: no sessions, no start time, empty response", async () => {
    api.admin.addVolunteer.mockResolvedValue(null);
    renderModal({
      event: {
        shifts: [{ id: "sh-x", name: "Bare", capacity: 2, current_count: 0 }],
        slots: [{ id: "or-x", slot_type: "orientation", capacity: 2, current_count: 0 }],
      },
    });
    await fillIdentity();
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Volunteer added."));
  });

  it("treats whitespace-only names as missing", async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText(/first name/i), "   ");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lopez");
    await userEvent.type(screen.getByLabelText(/^email$/i), "maya@example.com");
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    expect(screen.getByText(/first name, last name and email are required/i)).toBeInTheDocument();
    expect(api.admin.addVolunteer).not.toHaveBeenCalled();
  });

  it("trims names and email before sending", async () => {
    api.admin.addVolunteer.mockResolvedValue({ volunteer_id: "v-1", bookings: [] });
    renderModal();
    await userEvent.type(screen.getByLabelText(/first name/i), "  Maya ");
    await userEvent.type(screen.getByLabelText(/last name/i), " Lopez");
    await userEvent.type(screen.getByLabelText(/^email$/i), " maya@example.com ");
    await userEvent.type(screen.getByLabelText(/phone/i), "   ");
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    await waitFor(() => expect(api.admin.addVolunteer).toHaveBeenCalled());
    const body = api.admin.addVolunteer.mock.calls[0][1];
    expect(body).toMatchObject({
      first_name: "Maya", last_name: "Lopez", email: "maya@example.com", phone: null,
    });
  });

  it("blocks a double submit while the request is in flight", async () => {
    let resolve;
    api.admin.addVolunteer.mockReturnValue(new Promise((r) => { resolve = r; }));
    renderModal();
    await fillIdentity();
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    const busy = await screen.findByRole("button", { name: /adding/i });
    expect(busy).toBeDisabled();
    await userEvent.click(busy);
    expect(api.admin.addVolunteer).toHaveBeenCalledTimes(1);
    resolve({ volunteer_id: "v-1", bookings: [] });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("clears the previous error when submitted again", async () => {
    api.admin.addVolunteer.mockRejectedValueOnce(new Error("already on this shift"));
    api.admin.addVolunteer.mockResolvedValueOnce({ volunteer_id: "v-1", bookings: [] });
    renderModal();
    await fillIdentity();
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    expect(await screen.findByText(/already on this shift/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^add volunteer$/i }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(screen.queryByText(/already on this shift/i)).not.toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    renderModal({ open: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Cancel resets and closes", async () => {
    const { onClose } = renderModal();
    await userEvent.type(screen.getByLabelText(/first name/i), "Maya");
    await userEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
