import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TransportReconciliation from "./TransportReconciliation";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../hooks/useInactivityLogout", () => ({ useInactivityLogout: () => ({ showWarning: false, secondsLeft: 0, stayLoggedIn: jest.fn() }) }));

const cashItem = {
  kind: "payment", id: 51, method: "cash", status: "pending", reported_amount: "400.00",
  received_amount: "0.00", receipt: null, reference: "TR-ACCEPTANCE", remittance: null,
  remittance_status: "pending", queue_reasons: [], can_confirm_cash: true,
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 8, username: "clerk", is_staff: true, staff_role: "accountant" }, loading: false, logout: jest.fn() });
  api.get.mockResolvedValue({ data: [cashItem] });
  api.post.mockResolvedValue({ data: { id: 51, status: "confirmed", received_amount: "360.00" } });
});

test("clerk confirms the physically counted cash amount with a reason", async () => {
  render(<MemoryRouter><TransportReconciliation /></MemoryRouter>);
  expect(await screen.findByText("cash")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add review" }));
  fireEvent.change(screen.getByLabelText("Review reason"), { target: { value: "Counted cash at desk" } });
  fireEvent.change(screen.getByLabelText("Counted amount received (KES)"), { target: { value: "360.00" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm cash received" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/payment-queue/", expect.objectContaining({
    payment_id: 51, confirm: true, reason: "Counted cash at desk", received_amount: "360.00",
  })));
});

test("staff matches an unmatched receipt using an explicit reference and reason", async () => {
  api.get.mockResolvedValue({ data: [{ ...cashItem, method: "c2b", status: "unmatched", can_confirm_cash: false, can_match: true, received_amount: "400.00", receipt: "DARAJA-400" }] });
  render(<MemoryRouter><TransportReconciliation /></MemoryRouter>);
  expect(await screen.findByText("DARAJA-400")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add review" }));
  const match = screen.getByRole("button", { name: "Match payment" });
  expect(match).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Remittance reference"), { target: { value: "TR-VERIFIED" } });
  fireEvent.change(screen.getByLabelText("Review reason"), { target: { value: "Checked bank and shift references" } });
  fireEvent.click(match);
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/payment-queue/", {
    payment_id: 51, remittance_id: "TR-VERIFIED", reason: "Checked bank and shift references",
  }));
  expect(await screen.findByText("Reconciliation action saved.")).toBeInTheDocument();
});
