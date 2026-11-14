import React from "react";
import { render, screen } from "@testing-library/react";
import App from "./App";
import { useAuth } from "./context/AuthContext";

jest.mock("./context/AuthContext", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: jest.fn(),
}));
jest.mock("./context/SaccoContext", () => ({ SaccoProvider: ({ children }) => children }));
jest.mock("./pages/StaffWorkspaceDashboard", () => ({ workspace }) => <h1>{workspace}</h1>);
jest.mock("./pages/ChairmanDashboard", () => () => <h1>Chairman</h1>);
jest.mock("./pages/TransportOwner", () => () => <h1>Owner</h1>);
jest.mock("./pages/TransportCrew", () => () => <h1>Crew</h1>);
jest.mock("./pages/LoanCalculator", () => () => <h1>Loan calculator</h1>);
jest.mock("./pages/Welfare", () => () => <h1>Member welfare</h1>);
// /staff/welfare renders WelfareOfficer, not Welfare
jest.mock("./pages/WelfareOfficer", () => () => <h1>Welfare review</h1>);

const routes = [
  ["/staff/chairman", "operations.summary.read", "Chairman"],
  ["/staff/secretary", "members.review", "secretary"],
  ["/staff/treasury", "payments.reconcile", "treasurer"],
  ["/staff/credit", "loans.appraise_assigned", "credit_officer"],
  ["/staff/clerk", "transport.read_duties", "clerk"],
  ["/transport/owner", "transport.read_owned", "Owner"],
  ["/transport/crew", "transport.read_assigned", "Crew"],
  ["/loans/calculator", "loans.read_own", "Loan calculator"],
  ["/welfare", "welfare.read_own", "Member welfare"],
  ["/staff/welfare", "welfare.review", "Welfare review"],
];

test.each(routes)("router opens %s with its own server capability", (url, permission, heading) => {
  window.history.replaceState({}, "", url);
  useAuth.mockReturnValue({ user: { id: 3, permissions: [permission], workspaces: [] }, loading: false });
  render(<App />);
  expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
});

test.each(routes)("router denies %s without its server capability", (url, _permission, heading) => {
  window.history.replaceState({}, "", url);
  useAuth.mockReturnValue({ user: { id: 4, permissions: [], workspaces: [] }, loading: false });
  render(<App />);
  expect(screen.queryByRole("heading", { name: heading })).not.toBeInTheDocument();
  expect(screen.getByText(/This page is not available to your account/i)).toBeInTheDocument();
});
