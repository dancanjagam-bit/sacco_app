import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Savings from "./Savings";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../components/Layout", () => function MockLayout({ children }) { return <main>{typeof children === "function" ? children() : children}</main>; });

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { username: "member", phone_number: "0712345678", bosa_savings: "1250.00", fosa_savings: "850.00" }, refreshUser: jest.fn() });
  api.get.mockImplementation((url) => {
    if (url === "collateral/status/") return Promise.resolve({ data: { bosa_balance: "1250.00", fosa_balance: "850.00", fosa_withdrawable: "700.00", fosa_withdrawals_pending: "150.00", total_locked: "0.00" } });
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "exit-request/") return Promise.resolve({ data: { exit_request: null } });
    return Promise.resolve({ data: { entries: [], total_balance: "0.00" } });
  });
});

test("member deposits open the existing M-Pesa request flow, not the staff-only direct-deposit API", async () => {
  api.post.mockResolvedValueOnce({ data: { checkout_request_id: "checkout-test-1" } });
  render(<MemoryRouter><Savings /></MemoryRouter>);

  fireEvent.change(screen.getByLabelText("Amount (KES)"), { target: { value: "250" } });
  fireEvent.click(screen.getByRole("button", { name: /continue to m-pesa/i }));
  expect(await screen.findByRole("dialog", { name: /deposit to bosa/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /send m-pesa request/i }));

  await waitFor(() => expect(api.post).toHaveBeenCalledWith("payments/mpesa/stk/", {
    payment_type: "deposit", phone: "0712345678", amount: 250, account_type: "bosa",
  }));
  expect(api.post).not.toHaveBeenCalledWith("deposit/", expect.anything());
  expect(await screen.findByText(/Waiting for provider confirmation/i)).toBeInTheDocument();
});

test("withdrawals remain disabled and pending amounts are shown separately", async () => {
  render(<MemoryRouter><Savings /></MemoryRouter>);
  expect(await screen.findByText("FOSA withdrawal status")).toBeInTheDocument();
  expect(screen.getByText(/Live M-Pesa disbursement is not configured/i)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("Held for pending withdrawals").parentElement).toHaveTextContent("KES 150.00"));
  expect(screen.queryByRole("button", { name: /submit withdrawal/i })).not.toBeInTheDocument();
});

test("balance service failure does not turn unavailable amounts into zero", async () => {
  api.get.mockImplementation((url) => {
    if (url === "collateral/status/") return Promise.reject(new Error("offline"));
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "exit-request/") return Promise.resolve({ data: { exit_request: null } });
    return Promise.resolve({ data: { entries: [] } });
  });
  render(<MemoryRouter><Savings /></MemoryRouter>);
  expect(await screen.findByText(/Balance availability could not be refreshed/i)).toBeInTheDocument();
  expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
});

test("statement tab renders loading while its initial request is pending, then renders entries", async () => {
  let resolveStatement;
  api.get.mockImplementation((url) => {
    if (url === "savings/statement/") return new Promise(resolve => { resolveStatement = resolve; });
    if (url === "collateral/status/") return Promise.resolve({ data: { bosa_balance: "1250.00", fosa_balance: "850.00" } });
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "exit-request/") return Promise.resolve({ data: { exit_request: null } });
    return Promise.resolve({ data: {} });
  });
  render(<MemoryRouter><Savings /></MemoryRouter>);

  fireEvent.click(screen.getByRole("tab", { name: "Savings statement" }));
  expect(await screen.findByText("Loading savings statement…")).toBeInTheDocument();

  await act(async () => {
    resolveStatement({ data: { entries: [{
      id: 1, created_at: "2026-11-12T09:00:00Z", account_type: "fosa",
      type: "Deposit", amount: "250.00", balance: "850.00",
    }] } });
  });
  expect(screen.getByText("Deposit")).toBeInTheDocument();
});

test("a statement response with null entries displays an error instead of crashing", async () => {
  api.get.mockImplementation((url) => {
    if (url === "savings/statement/") return Promise.resolve({ data: { entries: null } });
    if (url === "collateral/status/") return Promise.resolve({ data: { bosa_balance: "1250.00", fosa_balance: "850.00" } });
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "exit-request/") return Promise.resolve({ data: { exit_request: null } });
    return Promise.resolve({ data: {} });
  });
  render(<MemoryRouter><Savings /></MemoryRouter>);

  fireEvent.click(screen.getByRole("tab", { name: "Savings statement" }));
  expect(await screen.findByText("Savings statement could not be loaded")).toBeInTheDocument();
  expect(screen.queryByText("No savings activity recorded")).not.toBeInTheDocument();
});
