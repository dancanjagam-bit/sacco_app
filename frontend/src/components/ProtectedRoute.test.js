import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import ProtectedRoute from "./ProtectedRoute";
import AdminRoute from "./AdminRoute";

jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));

const ready = (user) => useAuth.mockReturnValue({
  user,
  loading: false,
  authError: "",
  hasSessionToken: true,
});

describe("permission-aware routes", () => {
  test("crew permission opens the assigned-work route", () => {
    ready({
      permissions: ["transport.read_assigned"],
      workspaces: [{ id: "crew", path: "/transport/crew", label: "Transport crew" }],
      default_workspace: "crew",
    });

    render(
      <MemoryRouter initialEntries={["/transport/crew"]}>
        <Routes>
          <Route path="/transport/crew" element={<ProtectedRoute requiredPermission="transport.read_assigned"><p>Crew shift</p></ProtectedRoute>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("Crew shift")).toBeInTheDocument();
  });

  test("member without crew permission is redirected to the server-approved workspace", async () => {
    ready({
      permissions: ["accounts.read_own"],
      workspaces: [{ id: "member", path: "/dashboard", label: "Member services" }],
      default_workspace: "member",
    });

    render(
      <MemoryRouter initialEntries={["/transport/crew"]}>
        <Routes>
          <Route path="/transport/crew" element={<ProtectedRoute requiredPermission="transport.read_assigned"><p>Crew shift</p></ProtectedRoute>} />
          <Route path="/dashboard" element={<p>Member dashboard</p>} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText("Member dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Crew shift")).not.toBeInTheDocument();
  });

  test("KYC reviewer can open their module without generic staff-console access", () => {
    ready({ permissions: ["kyc.review"], workspaces: [] });

    render(
      <MemoryRouter initialEntries={["/admin/id-verifications"]}>
        <Routes>
          <Route path="/admin/id-verifications" element={<AdminRoute requiredPermission="kyc.review"><p>Identity review queue</p></AdminRoute>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("Identity review queue")).toBeInTheDocument();
  });

  test("direct staff route without its permission redirects to the permitted workspace", async () => {
    ready({
      permissions: ["accounts.read_own"],
      workspaces: [{ id: "member", path: "/dashboard", label: "Member services" }],
      default_workspace: "member",
    });

    render(
      <MemoryRouter initialEntries={["/admin/reconciliation"]}>
        <Routes>
          <Route path="/admin/reconciliation" element={<AdminRoute requiredPermission="payments.reconcile"><p>Reconciliation queue</p></AdminRoute>} />
          <Route path="/dashboard" element={<p>Member dashboard</p>} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText("Member dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Reconciliation queue")).not.toBeInTheDocument();
  });
});
