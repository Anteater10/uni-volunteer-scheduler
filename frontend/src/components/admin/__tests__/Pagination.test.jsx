import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import Pagination, { buildPageList } from "../Pagination";

describe("Pagination", () => {
  it("builds [1, …, 3,4,5,6,7, …, 47] for page=5/total=47", () => {
    const list = buildPageList(5, 47);
    expect(list).toEqual([1, "…", 3, 4, 5, 6, 7, "…", 47]);
  });

  it("renders prev, numbered buttons, and next", () => {
    const onChange = vi.fn();
    render(<Pagination page={5} totalPages={47} onChange={onChange} />);
    expect(screen.getByRole("navigation", { name: /pagination/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    fireEvent.click(screen.getByRole("button", { name: "6" }));
    expect(onChange).toHaveBeenCalledWith(6);
  });

  it("disables prev on first page", () => {
    render(<Pagination page={1} totalPages={10} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /previous page/i })).toBeDisabled();
  });

  it("renders nothing when totalPages <= 1", () => {
    const { container } = render(
      <Pagination page={1} totalPages={1} onChange={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
