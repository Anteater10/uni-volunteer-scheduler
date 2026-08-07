import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  act,
  fireEvent,
} from "@testing-library/react";
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
    const [evs, rest] = parseSseChunk(
      'event: token\ndata: "hi"\n\nevent: done\ndata:',
    );
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
    expect(
      screen.getByRole("button", { name: /open scitrek copilot/i }),
    ).toBeInTheDocument();
  });

  it("renders for organizer", () => {
    mockAuth = { role: "organizer", isAuthed: true };
    render(<CopilotFab />);
    expect(
      screen.getByRole("button", { name: /open scitrek copilot/i }),
    ).toBeInTheDocument();
  });

  it("hides for volunteer", () => {
    mockAuth = { role: "volunteer", isAuthed: true };
    render(<CopilotFab />);
    expect(
      screen.queryByRole("button", { name: /open scitrek copilot/i }),
    ).not.toBeInTheDocument();
  });

  it("hides when not authed", () => {
    mockAuth = { role: null, isAuthed: false };
    render(<CopilotFab />);
    expect(
      screen.queryByRole("button", { name: /open scitrek copilot/i }),
    ).not.toBeInTheDocument();
  });

  it("hides when flag is off", () => {
    vi.stubEnv("VITE_COPILOT_ENABLED", "false");
    render(<CopilotFab />);
    expect(
      screen.queryByRole("button", { name: /open scitrek copilot/i }),
    ).not.toBeInTheDocument();
  });

  it("opens the drawer when clicked", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "sess-1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CopilotFab />);
    await userEvent.click(
      screen.getByRole("button", { name: /open scitrek copilot/i }),
    );
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// CopilotDrawer — happy path streaming
// ---------------------------------------------------------------------------
describe("CopilotDrawer", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <CopilotDrawer open={false} onClose={() => {}} />,
    );
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
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );

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
              {
                event: "error",
                data: '{"error":"RuntimeError","message_id":"asst-2"}',
              },
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
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );

    await screen.findByText(/stream failed: runtimeerror/i);
  });

  // ---- Plan 32-06: citation chips wired below assistant messages ----
  it("renders citation chips from a meta event below the assistant message", async () => {
    const citations = [
      {
        chunk_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        source_path: "docs/a/01.md",
        char_start: 0,
        char_end: 5,
        quote: "alpha",
        rrf_score: 0.9,
        rerank_score: 0.9,
      },
      {
        chunk_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        source_path: "docs/b/02.md",
        char_start: 0,
        char_end: 5,
        quote: "beta",
        rrf_score: 0.8,
        rerank_score: 0.8,
      },
    ];
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-chips" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              {
                event: "meta",
                data: JSON.stringify({
                  citations,
                  retrieval_latency_ms: 12,
                  rerank_latency_ms: 34,
                }),
              },
              { event: "token", data: '"Answer"' },
              { event: "done", data: '{"message_id":"asst-chips"}' },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );

    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("Answer");

    const list = await screen.findByRole("list", {
      name: /sources consulted/i,
    });
    expect(list.className).toMatch(/overflow-x-auto/);
    expect(
      screen.getByRole("button", { name: /citation 1/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /citation 2/i }),
    ).toBeInTheDocument();
  });

  it("caps chips at 5 even when more citations arrive", async () => {
    const many = Array.from({ length: 8 }).map((_, i) => ({
      chunk_id: `cccccccc-cccc-cccc-cccc-cccccccccc0${i}`,
      source_path: `docs/many/${i}.md`,
      char_start: 0,
      char_end: 1,
      quote: `q${i}`,
      rrf_score: 0.5,
      rerank_score: 0.5,
    }));
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-many" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              {
                event: "meta",
                data: JSON.stringify({
                  citations: many,
                  retrieval_latency_ms: 1,
                  rerank_latency_ms: 1,
                }),
              },
              { event: "token", data: '"ok"' },
              { event: "done", data: '{"message_id":"asst-many"}' },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );
    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("ok");
    const chips = await screen.findAllByRole("button", {
      name: /citation \d+/i,
    });
    expect(chips).toHaveLength(5);
  });

  it("renders no chip section when meta carries empty citations", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-empty" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              {
                event: "meta",
                data: JSON.stringify({
                  citations: [],
                  retrieval_latency_ms: 1,
                  rerank_latency_ms: 1,
                }),
              },
              { event: "token", data: '"plain"' },
              { event: "done", data: '{"message_id":"asst-empty"}' },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );
    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("plain");
    expect(
      screen.queryByRole("list", { name: /sources consulted/i }),
    ).toBeNull();
  });

  it("clicking a chip opens CitationPanel, closing hides it", async () => {
    const citations = [
      {
        chunk_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
        source_path: "docs/d.md",
        char_start: 0,
        char_end: 3,
        quote: "delta",
        rrf_score: 1,
        rerank_score: 1,
      },
    ];
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-click" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              {
                event: "meta",
                data: JSON.stringify({
                  citations,
                  retrieval_latency_ms: 1,
                  rerank_latency_ms: 1,
                }),
              },
              { event: "token", data: '"ans"' },
              { event: "done", data: '{"message_id":"asst-click"}' },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      )
      // citation detail fetch
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            source_path: "docs/d.md",
            char_start: 0,
            char_end: 3,
            content: "delta-full-content",
            document_url: "",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("ans");
    await userEvent.click(screen.getByRole("button", { name: /citation 1/i }));
    await screen.findByText(/delta-full-content/);
    await userEvent.click(
      screen.getByRole("button", { name: /close source panel/i }),
    );
    await waitFor(() => {
      expect(screen.queryByText(/delta-full-content/)).toBeNull();
    });
  });

  // ---- Phase 33-09: tool-call indicator + confirmation card ----
  it("renders tool-call indicator and confirmation card from SSE, posts decision", async () => {
    const sseText = sseBlob([
      {
        event: "meta",
        data: JSON.stringify({
          citations: [],
          retrieval_latency_ms: 0,
          rerank_latency_ms: 0,
        }),
      },
      {
        event: "tool_call",
        data: JSON.stringify({
          type: "tool_call",
          call_id: "call-1",
          tool: "send_reminder_email",
          args: { to: "x@example.com" },
        }),
      },
      {
        event: "confirmation_request",
        data: JSON.stringify({
          type: "confirmation_request",
          call_id: "call-1",
          tool: "send_reminder_email",
          args: { to: "x@example.com" },
          preview: "Will email 1 participant",
        }),
      },
    ]);
    global.fetch = vi
      .fn()
      // 1: createSession
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-confirm" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      // 2: stream POST
      .mockResolvedValueOnce(
        new Response(streamFrom(sseText), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      )
      // 3: POST /confirm/call-1
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            call_id: "call-1",
            result: { ok: true },
            redactions: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "do the thing");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );

    // tool-call indicator
    await screen.findByRole("status", { name: /calling send_reminder_email/i });
    // confirmation card
    const confirmBtn = await screen.findByText("Confirm");
    await userEvent.click(confirmBtn);

    // POST hit /confirm/call-1 with approved=true
    await waitFor(() => {
      const calls = global.fetch.mock.calls;
      const confirmCall = calls.find((c) =>
        String(c[0]).includes("/confirm/call-1"),
      );
      expect(confirmCall).toBeDefined();
      const body = JSON.parse(confirmCall[1].body);
      expect(body.approved).toBe(true);
    });
    // card is removed
    await waitFor(() => {
      expect(screen.queryByText("Confirm")).toBeNull();
    });
  });

  // ---- K28: a tool that failed must not be labelled "ran" ----
  it("labels a failed tool call as failed, not as ran", async () => {
    const sseText = sseBlob([
      {
        event: "meta",
        data: JSON.stringify({
          citations: [],
          retrieval_latency_ms: 0,
          rerank_latency_ms: 0,
        }),
      },
      {
        event: "tool_call",
        data: JSON.stringify({
          type: "tool_call",
          call_id: "call-err",
          tool: "list_modules",
          args: { week: "next week" },
        }),
      },
      {
        event: "tool_result",
        data: JSON.stringify({
          type: "tool_result",
          call_id: "call-err",
          result: { error: "bad ISO week: 'next week'" },
          redactions: 0,
          error: true,
        }),
      },
      // The turn keeps going — that is the K28 change.
      {
        event: "token",
        data: JSON.stringify({ text: "Which week did you mean?" }),
      },
      { event: "done", data: JSON.stringify({}) },
    ]);
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-toolerr" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(streamFrom(sseText), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      );

    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "modules next week?");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );

    await screen.findByRole("status", { name: /failed list_modules/i });
    expect(
      screen.queryByRole("status", { name: /ran list_modules/i }),
    ).toBeNull();
  });

  it("posts approved=false on Reject click", async () => {
    const sseText = sseBlob([
      {
        event: "meta",
        data: JSON.stringify({
          citations: [],
          retrieval_latency_ms: 0,
          rerank_latency_ms: 0,
        }),
      },
      {
        event: "confirmation_request",
        data: JSON.stringify({
          type: "confirmation_request",
          call_id: "call-2",
          tool: "move_participant",
          args: { id: 1 },
          preview: "Will move 1",
        }),
      },
    ]);
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-reject" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(streamFrom(sseText), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ call_id: "call-2", status: "rejected" }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "x");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );

    const rejectBtn = await screen.findByText("Reject");
    await userEvent.click(rejectBtn);
    await waitFor(() => {
      const confirmCall = global.fetch.mock.calls.find((c) =>
        String(c[0]).includes("/confirm/call-2"),
      );
      expect(confirmCall).toBeDefined();
      expect(JSON.parse(confirmCall[1].body).approved).toBe(false);
    });
  });

  // ---- Phase 35-01-D Task 15: data-message-id on assistant bubbles ----
  it("stamps data-message-id from event: message_persisted on the assistant bubble", async () => {
    const PERSISTED = "9b0a0d6e-3e0f-4d3e-8d2a-1c0e8a7f7b00";
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-mp" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              { event: "token", data: '"Answer"' },
              {
                event: "message_persisted",
                data: JSON.stringify({ id: PERSISTED, role: "assistant" }),
              },
              { event: "done", data: `{"message_id":"${PERSISTED}"}` },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );

    const { container } = render(
      <CopilotDrawer open={true} onClose={() => {}} />,
    );
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("Answer");

    const stamped = container.querySelector(`[data-message-id="${PERSISTED}"]`);
    expect(stamped).not.toBeNull();
    expect(stamped.textContent).toContain("Answer");
  });

  it("does not stamp data-message-id on user bubbles", async () => {
    const PERSISTED = "11111111-2222-3333-4444-555555555555";
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-mp-user" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              { event: "token", data: '"ok"' },
              {
                event: "message_persisted",
                data: JSON.stringify({ id: PERSISTED, role: "assistant" }),
              },
              { event: "done", data: `{"message_id":"${PERSISTED}"}` },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );
    const { container } = render(
      <CopilotDrawer open={true} onClose={() => {}} />,
    );
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "my-question");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("ok");

    // Exactly one bubble has the id (the assistant's).
    const stamped = container.querySelectorAll(`[data-message-id]`);
    expect(stamped).toHaveLength(1);
    expect(stamped[0].textContent).toContain("ok");
  });

  it("falls back to done.message_id when no message_persisted event arrives (backwards compat)", async () => {
    // Old backends without 35-01-D still expose the persisted id via
    // `done.message_id` — the hook aliases it onto `id` so the bubble
    // still gets a stable data-message-id stamp.
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "sess-legacy" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              { event: "token", data: '"legacy"' },
              { event: "done", data: '{"message_id":"asst-legacy"}' },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );
    const { container } = render(
      <CopilotDrawer open={true} onClose={() => {}} />,
    );
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("legacy");
    expect(
      container.querySelector('[data-message-id="asst-legacy"]'),
    ).not.toBeNull();
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
    await userEvent.click(
      screen.getByRole("button", { name: /close copilot/i }),
    );
    expect(onClose).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// K32 — the drawer said role="dialog" and behaved like a div, and the rating
// modal it opens on close had no exit that led out. These are the escapes.
// ---------------------------------------------------------------------------
describe("CopilotDrawer — you can always get out", () => {
  function sessionOnly(id) {
    return vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ id }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }

  // Two halves, because the session-create call fires on render: the mock
  // has to be in place before the component mounts, and the turn has to be
  // driven after it.
  function mockTurn(id) {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          streamFrom(
            sseBlob([
              { event: "token", data: '"Answer"' },
              { event: "done", data: '{"message_id":"m1"}' },
            ]),
          ),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      )
      // the POST /close that closeAndDismiss fires
      .mockResolvedValue(new Response(null, { status: 204 }));
  }

  // Drives a full assistant turn, which is what arms the rating intercept.
  async function doTurn() {
    const input = await screen.findByLabelText("Message");
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.type(input, "hi");
    await userEvent.click(
      screen.getByRole("button", { name: /send message/i }),
    );
    await screen.findByText("Answer");
  }

  it("announces itself as a modal dialog", async () => {
    global.fetch = sessionOnly("sess-aria");
    render(<CopilotDrawer open={true} onClose={() => {}} />);
    const aside = screen.getByRole("dialog", { name: /scitrek copilot/i });
    expect(aside).toHaveAttribute("aria-modal", "true");
  });

  it("Escape closes a drawer with nothing to rate", async () => {
    const onClose = vi.fn();
    global.fetch = sessionOnly("sess-esc");
    render(<CopilotDrawer open={true} onClose={onClose} />);
    await screen.findByLabelText("Message");
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("Escape asks for a rating once there has been an answer", async () => {
    const onClose = vi.fn();
    mockTurn("sess-esc2");
    render(<CopilotDrawer open={true} onClose={onClose} />);
    await doTurn();
    fireEvent.keyDown(document, { key: "Escape" });
    await screen.findByRole("dialog", { name: /rate this session/i });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("Close without rating actually dismisses the drawer", async () => {
    // The trap this whole item is named for: before K32, reaching this
    // modal meant rating or staying. There was no third answer.
    const onClose = vi.fn();
    mockTurn("sess-dismiss");
    render(<CopilotDrawer open={true} onClose={onClose} />);
    await doTurn();
    await userEvent.click(
      screen.getByRole("button", { name: /close copilot/i }),
    );
    await screen.findByRole("dialog", { name: /rate this session/i });
    await userEvent.click(
      screen.getByRole("button", { name: /close without rating/i }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("keeps Tab inside the drawer", async () => {
    global.fetch = sessionOnly("sess-tab");
    render(<CopilotDrawer open={true} onClose={() => {}} />);
    await screen.findByLabelText("Message");
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    outside.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      screen.getByRole("dialog", { name: /scitrek copilot/i }),
    ).toContainElement(document.activeElement);
    outside.remove();
  });

  it("hands focus back to the control that opened it", async () => {
    global.fetch = sessionOnly("sess-restore");
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const { rerender } = render(
      <CopilotDrawer open={true} onClose={() => {}} />,
    );
    await screen.findByLabelText("Message");
    expect(document.activeElement).not.toBe(opener);
    rerender(<CopilotDrawer open={false} onClose={() => {}} />);
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
