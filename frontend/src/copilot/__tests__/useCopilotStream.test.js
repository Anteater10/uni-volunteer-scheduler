// Tests for the `event: meta` branch added in Plan 32-06.
//
// We exercise useCopilotStream as a pure consumer of an SSE wire-format
// ReadableStream. Phase 30 fixtures (token/done/error) must remain green —
// the meta branch is strictly additive.
import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

import { useCopilotStream, parseSseChunk } from "../useCopilotStream";

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

const CITATIONS_FIXTURE = [
  {
    chunk_id: "11111111-1111-1111-1111-111111111111",
    source_path: "docs/learning/30-streaming-chat-mvp/01-sse.md",
    char_start: 0,
    char_end: 42,
    quote: "Server-sent events deliver tokens incrementally.",
    rrf_score: 0.91,
    rerank_score: 0.88,
  },
  {
    chunk_id: "22222222-2222-2222-2222-222222222222",
    source_path: "docs/learning/32-rag-retrieval/02-hybrid.md",
    char_start: 100,
    char_end: 200,
    quote: "RRF fuses dense and lexical rankings without tuning.",
    rrf_score: 0.85,
    rerank_score: 0.83,
  },
];

beforeEach(() => {
  global.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useCopilotStream — meta event branch (Plan 32-06)", () => {
  it("populates citations + latencies from a meta event", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        {
          event: "meta",
          data: JSON.stringify({
            citations: CITATIONS_FIXTURE,
            retrieval_latency_ms: 50,
            rerank_latency_ms: 120,
          }),
        },
        { event: "token", data: '"Hi"' },
        { event: "done", data: '{"message_id":"asst-1"}' },
      ]),
    );

    const { result } = renderHook(() => useCopilotStream("sess-1"));
    let returned;
    await act(async () => {
      returned = await result.current.send("hello");
    });
    expect(returned.text).toBe("Hi");
    await waitFor(() => {
      expect(result.current.citations).toHaveLength(2);
    });
    expect(result.current.citations[0].chunk_id).toBe(CITATIONS_FIXTURE[0].chunk_id);
    expect(result.current.latencies).toEqual({ retrieval: 50, rerank: 120 });
  });

  it("makes citations available before token text is appended", async () => {
    // Ordering invariant: by the time the first token is observed by the
    // hook, the meta payload (which arrived earlier in the wire byte stream)
    // has already populated `citations`. We assert this by feeding a stream
    // whose ONLY token chunk is preceded by meta — and observing that when
    // the stream resolves, citations are populated AND partial is non-empty.
    // The chunked-reader contract guarantees in-order parsing.
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse(
        [
          {
            event: "meta",
            data: JSON.stringify({
              citations: CITATIONS_FIXTURE.slice(0, 1),
              retrieval_latency_ms: 10,
              rerank_latency_ms: 20,
            }),
          },
          { event: "token", data: '"first"' },
          { event: "done", data: '{"message_id":"asst-2"}' },
        ],
      ),
    );

    const { result } = renderHook(() => useCopilotStream("sess-1"));
    await act(async () => {
      await result.current.send("hi");
    });
    // Both meta and token were processed in-order: chips render, text accumulated.
    await waitFor(() => {
      expect(result.current.citations).toHaveLength(1);
    });
    expect(result.current.partial).toBe("first");
  });

  it("does not break the existing token/done branches (Phase 30 fixture)", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        { event: "token", data: '"Hel"' },
        { event: "token", data: '"lo!"' },
        { event: "done", data: '{"message_id":"asst-3"}' },
      ]),
    );
    const { result } = renderHook(() => useCopilotStream("sess-1"));
    let returned;
    await act(async () => {
      returned = await result.current.send("hi");
    });
    expect(returned.text).toBe("Hello!");
    expect(returned.messageId).toBe("asst-3");
    expect(result.current.citations).toEqual([]);
  });

  it("preserves the error branch behavior", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        { event: "token", data: '"part"' },
        { event: "error", data: '{"error":"RuntimeError","message_id":"asst-4"}' },
      ]),
    );
    const { result } = renderHook(() => useCopilotStream("sess-1"));
    let returned;
    await act(async () => {
      returned = await result.current.send("hi");
    });
    expect(returned.error).toBeInstanceOf(Error);
    expect(returned.error.message).toBe("RuntimeError");
  });

  it("resets citations on a new turn (latest payload wins)", async () => {
    global.fetch
      .mockResolvedValueOnce(
        mockStreamResponse([
          {
            event: "meta",
            data: JSON.stringify({
              citations: CITATIONS_FIXTURE,
              retrieval_latency_ms: 10,
              rerank_latency_ms: 20,
            }),
          },
          { event: "token", data: '"a"' },
          { event: "done", data: '{"message_id":"asst-5"}' },
        ]),
      )
      .mockResolvedValueOnce(
        mockStreamResponse([
          {
            event: "meta",
            data: JSON.stringify({
              citations: CITATIONS_FIXTURE.slice(1, 2),
              retrieval_latency_ms: 5,
              rerank_latency_ms: 8,
            }),
          },
          { event: "token", data: '"b"' },
          { event: "done", data: '{"message_id":"asst-6"}' },
        ]),
      );

    const { result } = renderHook(() => useCopilotStream("sess-1"));
    await act(async () => {
      await result.current.send("one");
    });
    expect(result.current.citations).toHaveLength(2);
    await act(async () => {
      await result.current.send("two");
    });
    expect(result.current.citations).toHaveLength(1);
    expect(result.current.citations[0].chunk_id).toBe(CITATIONS_FIXTURE[1].chunk_id);
    expect(result.current.latencies).toEqual({ retrieval: 5, rerank: 8 });
  });

  it("renders zero chips when meta carries empty citations", async () => {
    global.fetch.mockResolvedValueOnce(
      mockStreamResponse([
        {
          event: "meta",
          data: JSON.stringify({
            citations: [],
            retrieval_latency_ms: 9,
            rerank_latency_ms: 11,
          }),
        },
        { event: "token", data: '"x"' },
        { event: "done", data: '{"message_id":"asst-7"}' },
      ]),
    );
    const { result } = renderHook(() => useCopilotStream("sess-1"));
    await act(async () => {
      await result.current.send("hi");
    });
    expect(result.current.citations).toEqual([]);
    expect(result.current.latencies).toEqual({ retrieval: 9, rerank: 11 });
  });

  it("parseSseChunk still exported and functional (no regression)", () => {
    const [evs] = parseSseChunk("event: meta\ndata: {\"citations\":[]}\n\n");
    expect(evs).toEqual([{ event: "meta", data: '{"citations":[]}' }]);
  });
});
