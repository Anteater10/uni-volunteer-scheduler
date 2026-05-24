// Phase 35-01-D Task 14: useCopilotStream captures `event: message_persisted`.
//
// The backend now emits `event: message_persisted\ndata: {"id":"<uuid>","role":"assistant"}`
// immediately after persisting the assistant copilot_messages row and BEFORE the
// terminal `done`/`error` marker. The hook captures the id and surfaces it on
// the onDone/onError callback (and the send() return value) as `id` alongside
// `role: "assistant"` so the drawer can stamp `data-message-id` on the bubble.
//
// Strictly additive — the legacy `messageId` field (from `done.message_id`) is
// preserved for callers that have not yet migrated.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useCopilotStream } from "../useCopilotStream";

vi.mock("../../lib/authStorage", () => ({
  default: { getToken: () => "test-token" },
  getToken: () => "test-token",
}));

function sseBlob(events) {
  return events.map((e) => `event: ${e.event}\ndata: ${e.data}\n\n`).join("");
}

function streamFrom(text, { chunks = 2 } = {}) {
  const encoder = new TextEncoder();
  const size = Math.ceil(text.length / chunks);
  return new ReadableStream({
    start(controller) {
      for (let i = 0; i < chunks; i++) {
        controller.enqueue(encoder.encode(text.slice(i * size, (i + 1) * size)));
      }
      controller.close();
    },
  });
}

function mockStreamResponse(events) {
  return new Response(streamFrom(sseBlob(events)), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

const PERSISTED_UUID = "9b0a0d6e-3e0f-4d3e-8d2a-1c0e8a7f7b00";

beforeEach(() => {
  global.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useCopilotStream — message_persisted (Phase 35-01-D Task 14)", () => {
  it("captures the persisted id from `event: message_persisted` and exposes it on send() return", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        { event: "token", data: '"Hi"' },
        {
          event: "message_persisted",
          data: JSON.stringify({ id: PERSISTED_UUID, role: "assistant" }),
        },
        { event: "done", data: `{"message_id":"${PERSISTED_UUID}"}` },
      ]),
    );
    const { result } = renderHook(() => useCopilotStream("sess-1"));
    let returned;
    await act(async () => {
      returned = await result.current.send("hello");
    });
    expect(returned.id).toBe(PERSISTED_UUID);
    expect(returned.role).toBe("assistant");
    expect(returned.text).toBe("Hi");
    // Legacy alias preserved.
    expect(returned.messageId).toBe(PERSISTED_UUID);
  });

  it("threads `id` + `role` to the onDone callback", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        { event: "token", data: '"ok"' },
        {
          event: "message_persisted",
          data: JSON.stringify({ id: PERSISTED_UUID, role: "assistant" }),
        },
        { event: "done", data: `{"message_id":"${PERSISTED_UUID}"}` },
      ]),
    );
    const onDone = vi.fn();
    const { result } = renderHook(() => useCopilotStream("sess-1", { onDone }));
    await act(async () => {
      await result.current.send("hi");
    });
    expect(onDone).toHaveBeenCalledTimes(1);
    const arg = onDone.mock.calls[0][0];
    expect(arg.id).toBe(PERSISTED_UUID);
    expect(arg.role).toBe("assistant");
    expect(arg.text).toBe("ok");
  });

  it("threads `id` + `role` to onError when the stream fails after persist", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        { event: "token", data: '"part"' },
        {
          event: "message_persisted",
          data: JSON.stringify({ id: PERSISTED_UUID, role: "assistant" }),
        },
        {
          event: "error",
          data: `{"error":"RuntimeError","message_id":"${PERSISTED_UUID}"}`,
        },
      ]),
    );
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useCopilotStream("sess-1", { onError }),
    );
    let returned;
    await act(async () => {
      returned = await result.current.send("hi");
    });
    expect(returned.error).toBeInstanceOf(Error);
    expect(returned.id).toBe(PERSISTED_UUID);
    expect(returned.role).toBe("assistant");
    expect(onError).toHaveBeenCalledTimes(1);
    const info = onError.mock.calls[0][1];
    expect(info.id).toBe(PERSISTED_UUID);
    expect(info.role).toBe("assistant");
  });

  it("falls back to `done.message_id` when no `message_persisted` event arrives (backwards compat)", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        { event: "token", data: '"hi"' },
        { event: "done", data: `{"message_id":"${PERSISTED_UUID}"}` },
      ]),
    );
    const { result } = renderHook(() => useCopilotStream("sess-1"));
    let returned;
    await act(async () => {
      returned = await result.current.send("hello");
    });
    expect(returned.id).toBe(PERSISTED_UUID);
    expect(returned.role).toBe("assistant");
  });

  it("ignores a malformed message_persisted payload without breaking the stream", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        { event: "token", data: '"x"' },
        { event: "message_persisted", data: "not-json" },
        { event: "done", data: `{"message_id":"${PERSISTED_UUID}"}` },
      ]),
    );
    const { result } = renderHook(() => useCopilotStream("sess-1"));
    let returned;
    await act(async () => {
      returned = await result.current.send("hi");
    });
    // Falls back to the done payload's message_id.
    expect(returned.id).toBe(PERSISTED_UUID);
    expect(returned.text).toBe("x");
  });
});
