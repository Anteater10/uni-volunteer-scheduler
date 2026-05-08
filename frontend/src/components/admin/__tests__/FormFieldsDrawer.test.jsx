import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import FormFieldsDrawer from "../FormFieldsDrawer";

function renderDrawer(props = {}) {
  const defaults = {
    open: true,
    onClose: () => {},
    title: "Form fields",
    schema: [],
    onSave: vi.fn(),
  };
  return render(<FormFieldsDrawer {...defaults} {...props} />);
}

describe("FormFieldsDrawer", () => {
  it("renders existing schema as a table", () => {
    renderDrawer({
      schema: [
        { id: "foo", label: "Foo?", type: "text", required: true, order: 1 },
        {
          id: "color",
          label: "Favorite color",
          type: "select",
          options: ["red", "blue"],
          required: false,
          order: 2,
        },
      ],
    });
    expect(screen.getByText("Foo?")).toBeInTheDocument();
    expect(screen.getByText("Favorite color")).toBeInTheDocument();
    // Drawer renders fields as <li> list items (not a <table>) — one per
    // configured field.
    const items = screen.getAllByRole("listitem");
    expect(items.length).toBeGreaterThanOrEqual(2);
  });

  it("adds a field via the modal editor and includes it in save payload", async () => {
    const onSave = vi.fn();
    renderDrawer({ schema: [], onSave });

    // Drawer's top control is "+ Add question"; clicking opens the editor
    // modal whose submit button reads "Add field".
    fireEvent.click(screen.getByRole("button", { name: /add question/i }));
    const labelInput = screen.getByLabelText(/question/i);
    fireEvent.change(labelInput, { target: { value: "Emergency contact" } });
    fireEvent.click(screen.getByRole("button", { name: /^add field$/i }));

    // Field should appear in the table
    expect(screen.getByText("Emergency contact")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /save form fields/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const saved = onSave.mock.calls[0][0];
    expect(saved).toHaveLength(1);
    expect(saved[0].id).toBe("emergency_contact");
    expect(saved[0].label).toBe("Emergency contact");
    expect(saved[0].type).toBe("text");
  });

  it("deletes a field when delete is clicked", () => {
    const onSave = vi.fn();
    renderDrawer({
      schema: [
        { id: "foo", label: "Foo?", type: "text", required: false, order: 1 },
      ],
      onSave,
    });
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));
    fireEvent.click(screen.getByRole("button", { name: /save form fields/i }));
    expect(onSave).toHaveBeenCalledWith([]);
  });

  it("moves a field up when the up arrow is pressed", () => {
    const onSave = vi.fn();
    renderDrawer({
      schema: [
        { id: "a", label: "A", type: "text", order: 1 },
        { id: "b", label: "B", type: "text", order: 2 },
      ],
      onSave,
    });
    // Click "move up" on the second row (index 1 in display)
    const moveUpButtons = screen.getAllByRole("button", { name: /move up/i });
    // First button is disabled (first row), second is enabled
    const enabled = moveUpButtons.find((b) => !b.hasAttribute("disabled"));
    fireEvent.click(enabled);
    fireEvent.click(screen.getByRole("button", { name: /save form fields/i }));
    const saved = onSave.mock.calls[0][0];
    expect(saved.map((f) => f.id)).toEqual(["b", "a"]);
  });
});
