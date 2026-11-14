import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Reports from "./Reports";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../components/Layout", () => function MockLayout({ children }) { return <main>{typeof children === "function" ? children() : children}</main>; });

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ isAdmin: false, user: { transactions: [], loans: [] } });
  api.get.mockImplementation((path) => {
    if (path === "transactions/") return Promise.resolve({ data: {
      count: 50, results: [], summary: { deposits: "1234567.89", loans: "0.00", repayments: "25.00", withdrawals: "0.00", count: 50 },
    } });
    if (path === "dividends/") return Promise.resolve({ data: [] });
    return Promise.resolve({ data: {} });
  });
});

test("loan and dividend reports link transaction history and statements to their own screen", async () => {
  render(<MemoryRouter><Reports /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Loan and dividend reports" })).toBeInTheDocument();
  expect(api.get).not.toHaveBeenCalledWith("transactions/");
  expect(screen.getByRole("link", { name: /Transactions and statements/ })).toHaveAttribute("href", "/transactions");
  await waitFor(() => expect(api.get).toHaveBeenCalledWith("dividends/"));
});

test("reports show every approved loan separately and distinguish approval from disbursement", async () => {
  useAuth.mockReturnValue({ isAdmin: false, user: { transactions: [], loans: [
    { id: 21, amount: "5000.00", interest: "10.00", repayment_months: 3, balance: "5500.00", status: "approved" },
    { id: 22, amount: "12000.00", interest: "8.00", repayment_months: 6, balance: "12960.00", status: "approved" },
  ] } });
  render(<MemoryRouter><Reports /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Loan application #21" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Loan application #22" })).toBeInTheDocument();
  expect(screen.getByText(/not evidence that funds were sent/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Loan applications and recorded balances" })).toBeInTheDocument();
});

test("dividend load failure shows Retry and only a successful empty response shows empty state", async () => {
  api.get.mockImplementation((path) => {
    if (path === "transactions/") return Promise.resolve({ data: {
      count: 0, results: [], summary: { deposits: 0, loans: 0, repayments: 0, withdrawals: 0, count: 0 },
    } });
    if (path === "dividends/") {
      return api.get.mock.calls.filter(([calledPath]) => calledPath === "dividends/").length === 1
        ? Promise.reject(new Error("temporary failure"))
        : Promise.resolve({ data: [] });
    }
    return Promise.resolve({ data: {} });
  });
  render(<MemoryRouter><Reports /></MemoryRouter>);
  expect(await screen.findByText("Dividend history unavailable")).toBeInTheDocument();
  expect(screen.queryByText("No dividend records are available for this account.")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No dividend records are available for this account.")).toBeInTheDocument();
  expect(screen.queryByText("Dividend history unavailable")).not.toBeInTheDocument();
});
