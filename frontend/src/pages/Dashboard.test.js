import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Dashboard from "./Dashboard";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../components/Layout", () => function MockLayout({ children }) { return <main>{typeof children === "function" ? children() : children}</main>; });

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: {
    username: "member", first_name: "Miriam", member_number: "NW-1001", pending_loans: 0,
    bosa_savings: "1200.00", fosa_savings: "450.00", total_deposits: "2500.00",
    loans: [{ id: 4, status: "approved", balance: "900.00" }],
    transactions: [{ id: 20, type: "withdrawal", amount: "100.00", note: "Legacy FOSA debit", created_at: "2026-11-11T08:00:00Z", withdrawal_status: "needs_review" }],
  } });
  api.get.mockImplementation((url) => {
    if (url === "collateral/status/") return Promise.resolve({ data: { bosa_balance: "1200.00", fosa_balance: "450.00", fosa_withdrawable: "350.00", fosa_withdrawals_pending: "100.00" } });
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "loan/4/schedule/") return Promise.resolve({ data: { schedule: [{ installment: 1, expected: "800.00", paid: "200.00", due_date: "2026-12-01", status: "upcoming" }] } });
    return Promise.resolve({ data: {} });
  });
});

test("dashboard separates account values, held withdrawals, loans and the next due amount", async () => {
  render(<MemoryRouter><Dashboard /></MemoryRouter>);
  expect(await screen.findByRole("region", { name: "BOSA savings" })).toHaveTextContent("KES 1,200.00");
  expect(screen.getByRole("region", { name: "Total deposits recorded" })).toHaveTextContent("KES 2,500.00");
  const availableAccount = await screen.findByRole("region", { name: "Available FOSA" });
  await waitFor(() => expect(availableAccount).toHaveTextContent("KES 350.00"));
  expect(availableAccount).toHaveTextContent("Recorded FOSA balance");
  expect(availableAccount).toHaveTextContent("KES 450.00");
  expect(availableAccount).toHaveTextContent("Held for pending withdrawals");
  expect(availableAccount).toHaveTextContent("KES 100.00");
  expect(screen.getByRole("region", { name: "Balance on approved applications" })).toHaveTextContent("KES 900.00");
  expect(screen.getByRole("region", { name: "Balance on approved applications" })).toHaveTextContent("disbursement is not tracked");
  expect(screen.getByText("KES 600.00")).toBeInTheDocument();
  expect(screen.getByText("Needs review")).toBeInTheDocument();
  expect(api.get).not.toHaveBeenCalledWith("transport/crew/today/");
});

test("dashboard balance visibility control masks monetary values without changing account data", async () => {
  render(<MemoryRouter><Dashboard /></MemoryRouter>);
  await screen.findByText("KES 350.00");
  const hideButton = screen.getByRole("button", { name: "Hide balances" });
  fireEvent.click(hideButton);
  expect(screen.getByRole("button", { name: "Show balances" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("region", { name: "Available FOSA" })).toHaveTextContent("••••••");
  expect(screen.queryByText("KES 450.00")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show balances" }));
  expect(await screen.findByRole("region", { name: "Available FOSA" })).toHaveTextContent("KES 450.00");
});

test("missing schedule amounts do not appear as a zero due balance", async () => {
  api.get.mockImplementation((url) => {
    if (url === "collateral/status/") return Promise.resolve({ data: { bosa_balance: null, fosa_balance: null } });
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "loan/4/schedule/") return Promise.resolve({ data: { schedule: [{ installment: 1, due_date: "2026-12-01", status: "upcoming" }] } });
    return Promise.resolve({ data: {} });
  });
  render(<MemoryRouter><Dashboard /></MemoryRouter>);
  expect(await screen.findByText("Schedule status")).toBeInTheDocument();
  const nextRepayment = screen.getByText("Next repayment").closest(".repayment-panel");
  expect(nextRepayment.querySelector(".repayment-amount")).toHaveTextContent("Unavailable");
  expect(screen.queryByText("KES 0.00")).not.toBeInTheDocument();
});

test("dashboard balance failures are distinct from values and can be retried", async () => {
  let collateralCalls = 0;
  api.get.mockImplementation((url) => {
    if (url === "collateral/status/") {
      collateralCalls += 1;
      return collateralCalls === 1
        ? Promise.reject(new Error("temporary failure"))
        : Promise.resolve({ data: { bosa_balance: "1200.00", fosa_balance: "450.00", fosa_withdrawable: "350.00", fosa_withdrawals_pending: "100.00" } });
    }
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "loan/4/schedule/") return Promise.resolve({ data: { schedule: [] } });
    return Promise.resolve({ data: {} });
  });
  render(<MemoryRouter><Dashboard /></MemoryRouter>);
  expect(await screen.findByText("FOSA availability could not be refreshed")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.getByRole("region", { name: "Available FOSA" })).toHaveTextContent("KES 350.00"));
  expect(screen.queryByText("FOSA availability could not be refreshed")).not.toBeInTheDocument();
});

test("primary account actions remain available when the balance service fails", async () => {
  api.get.mockImplementation((url) => {
    if (url === "collateral/status/") return Promise.reject(new Error("temporary failure"));
    return Promise.resolve({ data: {} });
  });
  render(<MemoryRouter><Dashboard /></MemoryRouter>);

  expect(await screen.findByText("FOSA availability could not be refreshed")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Deposit/i })).toHaveAttribute("href", "/savings");
  expect(screen.getByRole("link", { name: /Withdraw/i })).toHaveAttribute("href", "/savings");
  expect(screen.getByRole("link", { name: /Apply for loan/i })).toHaveAttribute("href", "/loans");
  expect(screen.getByRole("link", { name: /Statements/i })).toHaveAttribute("href", "/transactions");
  expect(screen.getByRole("button", { name: "Refresh available FOSA funds" })).toBeInTheDocument();
});

test("a failed refresh never leaves old available or held amounts presented as current", async () => {
  let collateralCalls = 0;
  api.get.mockImplementation((url) => {
    if (url === "collateral/status/") {
      collateralCalls += 1;
      return collateralCalls === 1
        ? Promise.resolve({ data: { bosa_balance: "1200.00", fosa_balance: "450.00", fosa_withdrawable: "350.00", fosa_withdrawals_pending: "100.00" } })
        : Promise.reject(new Error("temporary failure"));
    }
    if (url === "withdrawals/") return Promise.resolve({ data: [] });
    if (url === "loan/4/schedule/") return Promise.resolve({ data: { schedule: [] } });
    return Promise.resolve({ data: {} });
  });
  render(<MemoryRouter><Dashboard /></MemoryRouter>);
  const availableAccount = await screen.findByRole("region", { name: "Available FOSA" });
  await waitFor(() => expect(availableAccount).toHaveTextContent("KES 350.00"));
  fireEvent.click(screen.getByRole("button", { name: "Refresh available FOSA funds" }));
  await waitFor(() => expect(availableAccount).toHaveTextContent("FOSA availability could not be refreshed"));
  expect(availableAccount).toHaveTextContent("Unavailable");
  expect(availableAccount).not.toHaveTextContent("KES 350.00");
  expect(availableAccount).not.toHaveTextContent("KES 100.00");
});

test("crew home shows the current shift returned by the transport assignment API", async () => {
  useAuth.mockReturnValue({ user: {
    username: "driver", first_name: "Miriam", transport_roles: ["driver"],
    vehicle_plate: "STALE PROFILE PLATE", route_name: "Stale profile route",
    loans: [], transactions: [],
  } });
  api.get.mockImplementation((url) => {
    if (url === "transport/crew/today/") return Promise.resolve({ data: {
      assignment: {
        vehicle_registration: "KCD 123X", route_name: "Nairobi West route",
        status: "active", status_label: "On shift",
      },
      message: "Current assignment returned.",
    } });
    if (url === "collateral/status/") return Promise.resolve({ data: { fosa_withdrawable: "4640.00" } });
    return Promise.resolve({ data: {} });
  });

  render(<MemoryRouter><Dashboard /></MemoryRouter>);

  const shift = await screen.findByLabelText("Today’s assigned shift");
  expect(api.get).toHaveBeenCalledWith("transport/crew/today/");
  await within(shift).findByText("KCD 123X");
  expect(shift).toHaveTextContent("KCD 123X");
  expect(shift).toHaveTextContent("Nairobi West route");
  expect(shift).toHaveTextContent("On shift");
  expect(shift).not.toHaveTextContent("STALE PROFILE PLATE");
  expect(shift).not.toHaveTextContent("Stale profile route");
  expect(screen.getByRole("link", { name: "Open shift" })).toHaveAttribute("href", "/transport/crew");
});

test("crew home explains a missing assignment instead of inventing a route or active status", async () => {
  useAuth.mockReturnValue({ user: {
    username: "driver", transport_roles: ["driver"], loans: [], transactions: [],
  } });
  api.get.mockImplementation((url) => {
    if (url === "transport/crew/today/") return Promise.resolve({ data: {
      assignment: null,
      message: "No transport assignment covers today.",
    } });
    if (url === "collateral/status/") return Promise.resolve({ data: {} });
    return Promise.resolve({ data: {} });
  });

  render(<MemoryRouter><Dashboard /></MemoryRouter>);

  const shift = await screen.findByLabelText("Today’s assigned shift");
  await within(shift).findByText("No current shift assignment");
  expect(shift).toHaveTextContent("No current shift assignment");
  expect(shift).toHaveTextContent("No transport assignment covers today.");
  expect(shift).not.toHaveTextContent("Nairobi West route");
  expect(shift).not.toHaveTextContent("Active");
  expect(screen.getByRole("link", { name: "View assignment help" })).toHaveAttribute("href", "/transport/crew");
});

test("crew shift failure has a retry path and retry displays the fresh API response", async () => {
  useAuth.mockReturnValue({ user: {
    username: "driver", transport_roles: ["driver"], loans: [], transactions: [],
  } });
  let shiftCalls = 0;
  api.get.mockImplementation((url) => {
    if (url === "transport/crew/today/") {
      shiftCalls += 1;
      return shiftCalls === 1
        ? Promise.reject(new Error("temporary error"))
        : Promise.resolve({ data: { assignment: {
          vehicle_registration: "KCD 123X", route_name: "Town Loop", status: "scheduled",
        } } });
    }
    if (url === "collateral/status/") return Promise.resolve({ data: {} });
    return Promise.resolve({ data: {} });
  });

  render(<MemoryRouter><Dashboard /></MemoryRouter>);

  const shift = await screen.findByLabelText("Today’s assigned shift");
  await within(shift).findByText("Shift information is unavailable.");
  expect(shift).toHaveTextContent("Shift information is unavailable.");
  fireEvent.click(within(shift).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(shift).toHaveTextContent("KCD 123X"));
  expect(shift).toHaveTextContent("Town Loop");
});
