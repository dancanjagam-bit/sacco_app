import React, { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ConfirmModal from "./ConfirmModal";

function ModalHarness({ loading = false }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open confirmation</button>
      {open && <ConfirmModal title="Confirm transfer" message="Review the action." loading={loading} onConfirm={() => {}} onCancel={() => setOpen(false)} />}
    </>
  );
}

test("confirmation dialog traps interaction, closes with Escape and restores focus", async () => {
  render(<ModalHarness />);
  const trigger = screen.getByRole("button", { name: "Open confirmation" });
  trigger.focus();
  fireEvent.click(trigger);

  const dialog = await screen.findByRole("alertdialog", { name: "Confirm transfer" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus());
  fireEvent.mouseDown(dialog);
  expect(dialog).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });

  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
  expect(document.body.style.overflow).toBe("");
});

test("a pending confirmation cannot be cancelled by Escape or the backdrop", async () => {
  render(<ModalHarness loading />);
  fireEvent.click(screen.getByRole("button", { name: "Open confirmation" }));
  const dialog = await screen.findByRole("alertdialog");
  fireEvent.keyDown(document, { key: "Escape" });
  fireEvent.mouseDown(dialog.parentElement);
  expect(dialog).toBeInTheDocument();
});
