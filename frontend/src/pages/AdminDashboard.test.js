import React from "react";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import AdminDashboard from "./AdminDashboard";

jest.mock("../api/axios", () => ({ get: jest.fn() }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../components/Layout", () => ({ children }) => <>{children}</>);
jest.mock("../components/MonthlyChart", () => ({ title, data }) => (
  <div role="img" aria-label={`${title}, ${data.length} months`} />
));

function renderDashboard() {
  return render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
}

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { username: "staff", first_name: "Staff", permissions: ["loans.appraise"] } });
});

test("uses only savings and loan data from the staff dashboard response", async () => {
  api.get.mockResolvedValue({ data: {
    total_savings: 12500,
    total_members: 9,
    active_loans: 3400,
    pending_loans: 2,
    approved_loans: 4,
    monthly_savings: [{ month: "Nov 2026", total: 1200 }],
    recent_transactions: [],
  } });

  renderDashboard();

  expect(await screen.findByText("KES 12,500.00")).toBeInTheDocument();
  expect(screen.getByText("Member savings recorded · all time")).toBeInTheDocument();
  expect(screen.getByText("No recent activity")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Monthly savings amounts, 1 months" })).toBeInTheDocument();
  const metrics = screen.getByRole("region", { name: "Recorded operational metrics" });
  expect(within(metrics).getAllByRole("region")).toHaveLength(3);
  expect(within(metrics).getByRole("region", { name: "Registered member records" })).toBeInTheDocument();
  expect(within(metrics).getByRole("region", { name: "Approved applications" })).toBeInTheDocument();
  expect(screen.queryByText(/confirmed collections/i)).not.toBeInTheDocument();
  expect(screen.getByText(/does not confirm loan disbursement/i)).toBeInTheDocument();
});

test("missing monthly and activity data remain unavailable instead of empty", async () => {
  api.get.mockResolvedValue({ data: { total_savings: null, pending_loans: null } });

  renderDashboard();

  expect(await screen.findByText("Monthly savings data unavailable")).toBeInTheDocument();
  expect(screen.getByText("Recent activity unavailable")).toBeInTheDocument();
  expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(1);
  expect(screen.queryByText("No monthly savings entries")).not.toBeInTheDocument();
  expect(screen.queryByText("No recent activity")).not.toBeInTheDocument();
});

test("failed dashboard request shows an error and never reports a successful empty state", async () => {
  api.get.mockRejectedValue(new Error("offline"));

  renderDashboard();

  expect(await screen.findByText("Dashboard unavailable")).toBeInTheDocument();
  expect(screen.queryByText("No recent activity")).not.toBeInTheDocument();
});
