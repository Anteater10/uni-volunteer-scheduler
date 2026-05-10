import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CopilotDrawer from "../CopilotDrawer";
import CopilotFab from "../CopilotFab";
import { parseSseChunk } from "../useCopilotStream";

// ---------------------------------------------------------------------------
// Auth context mock — drives FAB visibility
// ---------------------------------------------------------------------------
let mockAuth = { role: "admin", isAuthed: true };
vi.mock("../../state/useAuth", () => ({
  useAuth: () => mockAuth,
}));

// Token storage stub so api.js / useCopilotStream don't crash.
vi.mock("../../lib/authStorage", () => ({
  default: { getToken: () => "test-token" },
  getToken: () => "test-token",
}));

// ---------------------------------------------------------------------------
// SSE encode helper — emits the exact wire format the backend produces
// ---------------------------------------------------------------------------
function sseBlob(events) {
  return events.map((e) => `event: ${e.event}\ndata: ${e.data}\n\n`).join("");
}

function streamFrom(text) {
  // Split into a few chunks so the parser sees multiple reads.
  const encoder = new TextEncoder();
  const half = Math.ceil(text.length / 2);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text.slice(0, half)));
      controller.enqueue(encoder.encode(text.slice(half)));
      controller.close();
    },
  });
}

beforeEach(() => {
  mockAuth = { role: "admin", isAuthed: true };
  global.fetch = vi.fn();
  vi.stubEnv("VITE_COPILOT_ENABLED", "true");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// parseSseChunk — pure function, easiest unit
// ---------------------------------------------------------------------------
describe("parseSseChunk", () => {
  it("returns empty when no terminator yet", () => {
    const [evs, rest] = parseSseChunk("event: token\ndata: hi");
    expect(evs).toEqual([]);
    expect(rest).toContain("hi");
  });

  it("parses one full event and keeps remainder", () => {
    const [evs, rest] = parseSseChunk("event: token\ndata: \"hi\"\n\nevent: done\ndata:");
    expect(evs).toEqual([{ event: "token", data: '"hi"' }]);
    expect(rest).toContain("done");
  });

  it("skips blocks with no data line", () => {
    const [evs] = parseSseChunk("event: heartbeat\n\n");
    expect(evs).toEqual([]);
  });

  it("defaults event name to 'message' when only data is present", () => {
    const [evs] = parseSseChunk("data: hi\n\n");
    expect(evs).toEqual([{ event: "message", data: "hi" }]);
  });
});

// ---------------------------------------------------------------------------
// CopilotFab — visibility rules
// ---------------------------------------------------------------------------
describe("CopilotFab visibility", () => {
  it("renders for admin when flag is on", () => {
    render(<CopilotFab />);
    expect(screen.getByRole("button", { name: /open scitrek copilot/i })).toBeInTheDocument();
  });

  it("renders for organizer", () => {
    mockAuth = { role: "organizer", isAuthed: true };
    render(<CopilotFab />);
    expect(screen.getByRole("button", { name: /open scitrek copilot/i })).toBeInTheDocument();
  });

  it("hides for volunteer", () => {
    mockAuth = { role: "volunteer", isAuthed: true };
    render(<CopilotFab />);
    expect(screen.queryByRole("button", { name: /open scitrek copilot/i })).not.toBeInTheDocument();
  });

  it("hides when not authed", () => {
    mockAuth = { role: null, isAuthed: false };
    render(<CopilotFab />);
    expect(screen.queryByRole("button", { name: /open scitrek copilot/i })).not.toBeInTheDocument();
  });

  it("hides when flag is off", () => {
    vi.stubEnv("VITE_COPILOT_ENABLED", "false");
    render(<CopilotFab />);
    expect(screen.queryByRole("button", { name: /open scitrek copilot/i })).not.toBeInTheDocument();
  });

  it("opens the drawer when clicked", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "sess-1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CopilotFab />);
    await userEvent.click(screen.getByRole("button", { name: /open scitrek copilot/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// CopilotDrawer — happy path streaming
// ---------------------------------------------------------------------------
describe("CopilotDrawer", () => {
  it("renders nothing when closed", () => {
    const { container } = render(<CopilotDrawer open={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("creates a session on open and shows starting state then input", async () => {
    let resolveCreate;
    global.fetch = vi.fn().mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveCreate = () =>
            resolve(
              new Response(JSON.stringify({ id: "sess-2" }), {
                status: 201,
                headers: { "Content-Type": "application/json" },
              }),
            );
        }),
    );
    render(<CopilotDrawer open={true} onClose={() => {}} />);
    expect(screen.getByText(/starting session/i)).toBeInTheDocument();
    await act(async () => {
      resolveCreate();
    });
    await waitFor(() => {
      expect(screen.queryByText(/starting session/i)).not.toBeInTheDocument();
    });
    expect(screen.getByLabelText("Message")).not.toBeDisabled();
  });

  it("surfaces session-create errors", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "boom" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CopilotDrawer open={true} onClose={() => {}} />);
    await screen.findByText(/could not start a copilot session/i);
  });

  it("streams tokens and persists the assistant message", async () => {
    global.fetch = vi
      .fn()
      // 1: createSession
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-3" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      // 2: stream POST
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              { event: "token", data: '"Hel"' },
              { event: "token", data: '"lo!"' },
              { event: "done", data: '{"message_id":"asst-1"}' },
            ]),
          ),
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      );

    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi there");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));

    // user bubble appears
    expect(await screen.findByText("hi there")).toBeInTheDocument();
    // assembled assistant content lands after stream done
    await screen.findByText("Hello!");
  });

  it("renders an error chip when the stream fails mid-flight", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-4" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              { event: "token", data: '"part"' },
              { event: "error", data: '{"error":"RuntimeError","message_id":"asst-2"}' },
            ]),
          ),
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      );

    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));

    await screen.findByText(/stream failed: runtimeerror/i);
  });

  it("invokes onClose when the close button is clicked", async () => {
    const onClose = vi.fn();
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "sess-5" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CopilotDrawer open={true} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: /close copilot/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
