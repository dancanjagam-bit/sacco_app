import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import TransportOwner from "./TransportOwner";
import api from "../api/axios";

jest.mock("../api/axios", () => ({ get: jest.fn() }));
jest.mock("../components/Layout", () => ({ children }) => children);

test("owner detail shows outstanding amounts and the account entries linked to the remittance receipt", async () => {
  const payment = {
    id: 7, method: "cash", status: "confirmed", received_amount: "600.00", reported_amount: "600.00", receipt: "CASH-7",
    accounting_status: "posted", receipt_journal_id: 44,
    journal_allocations: [
      { category: "savings", amount: "200.00", journal_entry_id: 45 },
      { category: "loan_repayment", amount: "300.00", journal_entry_id: 45 },
      { category: "welfare_contribution", amount: "100.00", journal_entry_id: 45 },
    ],
  };
  const remittance = { id: "R6", payment_reference: "TR-6", status: "partial", amount: "800.00", received_amount: "600.00", outstanding_amount: "200.00", payments: [payment] };
  api.get.mockImplementation((url) => Promise.resolve({ data: url.endsWith("receipt/") ? { ...remittance, reported_amount: remittance.amount } : {
    id: 14, registration: "KAA 100B", operational_status: "available", reported_collections_today: "900.00", approved_expenses_today: "100.00",
    expected_remittances: "800.00", confirmed_receipts: "600.00", pending_remittance_amount: "200.00", expected_amount_unavailable_count: 1,
    remittances: [remittance], assignments: [],
  } }));
  render(<MemoryRouter initialEntries={["/transport/owner/vehicles/14"]}>
    <Routes><Route path="/transport/owner/vehicles/:vehicleId" element={<TransportOwner />} /></Routes>
  </MemoryRouter>);
  expect(await screen.findByText("Gross collections reported today")).toBeInTheDocument();
  expect(screen.getByText("Approved expenses today")).toBeInTheDocument();
  expect(screen.getByText("Available")).toBeInTheDocument();
  expect(screen.getByText("Some expected amounts need review")).toBeInTheDocument();
  expect(screen.getByText(/Receipt journal #44/)).toBeInTheDocument();
  expect(screen.getByText(/Savings · KES 200.00 · Journal #45/)).toBeInTheDocument();
  expect(screen.getByText(/Loan repayment · KES 300.00 · Journal #45/)).toBeInTheDocument();
  expect(screen.getByText(/Welfare contribution · KES 100.00 · Journal #45/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "View remittance receipt" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledWith("transport/remittances/R6/receipt/"));
  expect(await screen.findByRole("heading", { name: "TR-6" })).toBeInTheDocument();
});
