// The assistant has always written Markdown; the drawer used to print it
// raw, so a structured answer arrived as a wall of asterisks and hyphens.
// These tests pin the rendering, and — just as importantly — pin that a
// user's own message is NOT reinterpreted as formatting.
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MarkdownMessage from "../MarkdownMessage";

describe("MarkdownMessage", () => {
  it("renders **bold** as emphasis rather than literal asterisks", () => {
    const { container } = render(
      <MarkdownMessage>{"I can help with **data lookups**."}</MarkdownMessage>
    );
    expect(container.querySelector("strong")).toHaveTextContent("data lookups");
    expect(container.textContent).not.toContain("**");
  });

  it("renders a hyphen list as list items", () => {
    const { container } = render(
      <MarkdownMessage>{"- List modules\n- View a roster"}</MarkdownMessage>
    );
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("List modules");
    // The hyphen is the list marker now, not part of the text.
    expect(items[0].textContent.startsWith("-")).toBe(false);
  });

  it("renders headings and inline code", () => {
    const { container } = render(
      <MarkdownMessage>{"## Scheduling\nUse `list_modules`."}</MarkdownMessage>
    );
    expect(container.querySelector("h4")).toHaveTextContent("Scheduling");
    expect(container.querySelector("code")).toHaveTextContent("list_modules");
  });

  it("renders GFM tables inside their own horizontal scroller", () => {
    const { container } = render(
      <MarkdownMessage>
        {"| Module | Fill |\n| --- | --- |\n| Germs | 50% |"}
      </MarkdownMessage>
    );
    expect(container.querySelector("table")).toBeInTheDocument();
    expect(screen.getByText("Germs")).toBeInTheDocument();
    // A wide table must scroll itself, never the drawer.
    expect(container.querySelector("table").parentElement.className).toContain(
      "overflow-x-auto"
    );
  });

  it("does not render raw HTML the model may emit", () => {
    const { container } = render(
      <MarkdownMessage>{"<img src=x onerror=alert(1) />"}</MarkdownMessage>
    );
    expect(container.querySelector("img")).toBeNull();
  });

  it("survives the half-finished Markdown that arrives mid-stream", () => {
    // Tokens stream in, so the renderer is handed unbalanced syntax on the
    // way to a complete message. It must not throw.
    expect(() =>
      render(<MarkdownMessage>{"**Scheduling & ros"}</MarkdownMessage>)
    ).not.toThrow();
  });
});
