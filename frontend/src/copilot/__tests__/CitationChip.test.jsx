// Tests for CitationChip + CitationPanel (Plan 32-06).
import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CitationChip from "../CitationChip";
import CitationPanel from "../CitationPanel";

vi.mock("../../lib/authStorage", () => ({
  default: { getToken: () => "test-token" },
  getToken: () => "test-token",
}));

const CITATION = {
  chunk_id: "11111111-1111-1111-1111-111111111111",
  source_path: "docs/learning/30-streaming-chat-mvp/01-sse.md",
  char_start: 0,
  char_end: 42,
  quote:
    "Server-sent events deliver tokens incrementally. " +
    "The chunked transfer encoding keeps the connection open. ".repeat(5),
  rrf_score: 0.91,
  rerank_score: 0.88,
};

describe("CitationChip", () => {
  it("renders the [N] index and the filename only (not the full path)", () => {
    render(<CitationChip index={1} citation={CITATION} onClick={() => {}} />);
    expect(screen.getByText(/\[1\]/)).toBeInTheDocument();
    expect(screen.getByText(/01-sse\.md/)).toBeInTheDocument();
    // Full path should NOT be a text node — only on hover (title attr).
    expect(screen.queryByText("docs/learning/30-streaming-chat-mvp/01-sse.md")).toBeNull();
  });

  it("exposes the full source_path via the title attribute (tooltip)", () => {
    render(<CitationChip index={2} citation={CITATION} onClick={() => {}} />);
    const chip = screen.getByRole("button", { name: /citation 2/i });
    expect(chip.getAttribute("title")).toContain("Server-sent events");
  });

  it("calls onClick with the chunk_id when activated", async () => {
    const handler = vi.fn();
    render(<CitationChip index={1} citation={CITATION} onClick={handler} />);
    await userEvent.click(screen.getByRole("button", { name: /citation 1/i }));
    expect(handler).toHaveBeenCalledWith(CITATION.chunk_id);
  });

  it("is keyboard accessible (tabIndex, role=button)", async () => {
    const handler = vi.fn();
    render(<CitationChip index={1} citation={CITATION} onClick={handler} />);
    const chip = screen.getByRole("button", { name: /citation 1/i });
    expect(chip.getAttribute("tabIndex")).toBe("0");
    chip.focus();
    await userEvent.keyboard("{Enter}");
    expect(handler).toHaveBeenCalledWith(CITATION.chunk_id);
    await userEvent.keyboard(" ");
    expect(handler).toHaveBeenCalledTimes(2);
  });
});

describe("CitationPanel", () => {
  const FETCH_PAYLOAD = {
    source_path: "docs/learning/30-streaming-chat-mvp/01-sse.md",
    char_start: 0,
    char_end: 42,
    content: "Full source content — long form text…",
    document_url: "https://github.com/example/repo/blob/main/docs/learning/30-streaming-chat-mvp/01-sse.md",
  };

  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses honest header copy: "Source consulted"', async () => {
    global.fetch.mockResolvedValueOnce(
      new Response(JSON.stringify(FETCH_PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CitationPanel chunkId={CITATION.chunk_id} onClose={() => {}} />);
    expect(await screen.findByText(/source consulted/i)).toBeInTheDocument();
  });

  it("fetches and renders the source content + char range", async () => {
    global.fetch.mockResolvedValueOnce(
      new Response(JSON.stringify(FETCH_PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CitationPanel chunkId={CITATION.chunk_id} onClose={() => {}} />);
    await screen.findByText(/Full source content/);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/copilot/citations/${CITATION.chunk_id}`),
      expect.objectContaining({ method: "GET" }),
    );
    expect(screen.getByText(/0\s*[-–]\s*42/)).toBeInTheDocument();
  });

  it("shows the external link button only when document_url is non-empty", async () => {
    global.fetch.mockResolvedValueOnce(
      new Response(JSON.stringify(FETCH_PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CitationPanel chunkId={CITATION.chunk_id} onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByRole("link", { name: /open source/i })).toBeInTheDocument();
    });
  });

  it("hides the external link when document_url is empty", async () => {
    global.fetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ ...FETCH_PAYLOAD, document_url: "" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<CitationPanel chunkId={CITATION.chunk_id} onClose={() => {}} />);
    await screen.findByText(/Full source content/);
    expect(screen.queryByRole("link", { name: /open source/i })).toBeNull();
  });

  it("invokes onClose when the close button is clicked", async () => {
    global.fetch.mockResolvedValueOnce(
      new Response(JSON.stringify(FETCH_PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const onClose = vi.fn();
    render(<CitationPanel chunkId={CITATION.chunk_id} onClose={onClose} />);
    await screen.findByText(/Full source content/);
    await userEvent.click(screen.getByRole("button", { name: /close source panel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("surfaces a fetch error inline (does not crash)", async () => {
    global.fetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<CitationPanel chunkId={CITATION.chunk_id} onClose={() => {}} />);
    await screen.findByText(/could not load source/i);
  });
});
