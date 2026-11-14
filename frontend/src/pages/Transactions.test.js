import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Transactions from "./Transactions";
import api from "../api/axios";
import { downloadStatement } from "../utils/downloadStatement";

jest.mock("../api/axios", () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock("../components/Layout", () => function MockLayout({ children }) { return <main>{typeof children === "function" ? children() : children}</main>; });
jest.mock("../utils/downloadStatement", () => ({
  downloadStatement: jest.fn().mockResolvedValue("statement.pdf"),
  downloadFailureMessage: jest.fn().mockResolvedValue("Unable to download statement."),
}));

const pageData = {
  count: 1,
  next: null,
  previous: null,
  summary: { deposits: 0, loans: 0, repayments: 0, withdrawals: 300, count: 1 },
  results: [{
    id: 12, type: "withdrawal", amount: "300.00", note: "Legacy FOSA withdrawal",
    created_at: "2026-11-11T10:15:00Z", withdrawal_status: "needs_review",
    withdrawal_reference: null, withdrawal_destination: null, provider_reference: null,
  }],
};

beforeEach(() => {
  jest.clearAllMocks();
  api.get.mockResolvedValue({ data: pageData, headers: { "content-type": "application/pdf" } });
});

test("legacy withdrawal history is marked for review and details avoid inventing payout facts", async () => {
  render(<MemoryRouter><Transactions /></MemoryRouter>);
  expect(await screen.findByText("Needs review")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Details" }));
  expect(screen.getByText("Legacy FOSA withdrawal")).toBeInTheDocument();
  expect(screen.getAllByText("Not recorded on this entry").length).toBe(2);
  expect(screen.getByText(/contact the SACCO and provide this ledger reference/i)).toBeInTheDocument();
});

test("loan application activity is not presented as a confirmed disbursement", async () => {
  api.get.mockResolvedValueOnce({ data: {
    ...pageData,
    count: 1,
    summary: { deposits: 0, loans: "5000.00", repayments: 0, withdrawals: 0, count: 1 },
    results: [{
      id: 18, type: "loan", amount: "5000.00", note: "Loan #18 application",
      created_at: "2026-11-11T10:15:00Z",
    }],
  } });
  render(<MemoryRouter><Transactions /></MemoryRouter>);
  const row = (await screen.findByText("Loan application")).closest("tr");
  expect(row).toHaveTextContent("Application recorded");
  expect(row.querySelector(".ui-money")).toHaveTextContent("KES 5,000.00");
  expect(row.querySelector(".ui-money")).not.toHaveTextContent("+");
  expect(screen.getByRole("region", { name: "Account activity totals" })).toHaveTextContent("not confirmed disbursements");
});

test("filters use the member transaction API and both statement formats use authenticated API requests", async () => {
  render(<MemoryRouter><Transactions /></MemoryRouter>);
  await screen.findByText("Legacy FOSA withdrawal");
  fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-11-01" } });
  fireEvent.change(screen.getByLabelText("To date"), { target: { value: "2026-11-12" } });
  fireEvent.change(screen.getByLabelText("Type"), { target: { value: "withdrawal" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

  await waitFor(() => expect(api.get).toHaveBeenCalledWith("transactions/", {
    params: { page: 1, type: "withdrawal", from: "2026-11-01", to: "2026-11-12" },
  }));

  fireEvent.click(screen.getByRole("button", { name: "PDF statement" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledWith("statement/pdf/", {
    responseType: "blob", params: { from: "2026-11-01", to: "2026-11-12" },
  }));
  fireEvent.click(screen.getByRole("button", { name: "Excel statement" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledWith("transactions/excel/", {
    responseType: "blob", params: { from: "2026-11-01", to: "2026-11-12" },
  }));
  expect(downloadStatement).toHaveBeenCalledTimes(2);
});
