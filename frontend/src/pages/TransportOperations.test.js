import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TransportOperations from "./TransportOperations";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../hooks/useInactivityLogout", () => ({ useInactivityLogout: () => ({ showWarning: false, secondsLeft: 0, stayLoggedIn: jest.fn() }) }));

const staffUsers = [
  { id: 1, username: "owner", name: "Vehicle Owner", transport_roles: ["owner"] },
  { id: 2, username: "driver", name: "Assigned Driver", transport_roles: ["driver"] },
  { id: 3, username: "conductor", name: "Assigned Conductor", transport_roles: ["conductor"] },
];
const resources = {
  "transport/staff/users/": staffUsers,
  "transport/routes/": [{ id: 4, name: "Town Loop", origin: "Town", destination: "Market" }],
  "transport/vehicles/": [{ id: 5, registration: "KAA 123A", owner: 1, active: true }],
  "transport/assignments/": [],
  "transport/assignment-issues/": [],
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 10, username: "secretary", is_staff: true, staff_role: "secretary" }, loading: false, logout: jest.fn() });
  api.get.mockImplementation((url) => Promise.resolve({ data: resources[url] }));
  api.post.mockResolvedValue({ data: { id: 88 } });
});

test("staff can grant roles and the setup form selects role-qualified owners and crew", async () => {
  render(<MemoryRouter><TransportOperations /></MemoryRouter>);
  await screen.findByLabelText("Existing user");
  const ownerSelect = screen.getByLabelText("Vehicle owner");
  expect(ownerSelect).toHaveTextContent("Vehicle Owner");
  expect(ownerSelect).not.toHaveTextContent("Assigned Driver");
  const driverSelect = screen.getByLabelText("Driver");
  expect(driverSelect).toHaveTextContent("Assigned Driver");
  expect(driverSelect).not.toHaveTextContent("Vehicle Owner");

  fireEvent.change(screen.getByLabelText("Existing user"), { target: { value: "3" } });
  fireEvent.change(screen.getByLabelText("Role", { selector: "select" }), { target: { value: "driver" } });
  fireEvent.change(screen.getByLabelText("Reason for granting this role"), { target: { value: "Training approved" } });
  fireEvent.click(screen.getByRole("button", { name: "Assign role" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/roles/", { user: "3", role: "driver", reason: "Training approved" }));
});

test("staff creates a route, a vehicle, and a driver assignment with no conductor", async () => {
  render(<MemoryRouter><TransportOperations /></MemoryRouter>);
  await screen.findByLabelText("Route name");
  fireEvent.change(screen.getByLabelText("Route name"), { target: { value: "West Loop" } });
  fireEvent.change(screen.getByLabelText("Origin"), { target: { value: "Westlands" } });
  fireEvent.change(screen.getByLabelText("Destination"), { target: { value: "Town" } });
  fireEvent.click(screen.getByRole("button", { name: "Create route" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/routes/", { name: "West Loop", origin: "Westlands", destination: "Town" }));

  fireEvent.change(screen.getByLabelText("Registration"), { target: { value: "KDD 300B" } });
  fireEvent.change(screen.getByLabelText("Vehicle owner"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Register vehicle" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/vehicles/", { registration: "KDD 300B", owner: "1", make_model: "" }));

  fireEvent.change(screen.getByLabelText("Vehicle", { selector: "select" }), { target: { value: "5" } });
  fireEvent.change(screen.getByLabelText("Route", { selector: "select" }), { target: { value: "4" } });
  fireEvent.change(screen.getByLabelText("Driver", { selector: "select" }), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Starts at (Nairobi time)"), { target: { value: "2026-11-12T08:00" } });
  fireEvent.change(screen.getByLabelText("Ends at (Nairobi time)"), { target: { value: "2026-11-12T17:00" } });
  fireEvent.click(screen.getByRole("button", { name: "Create assignment" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/assignments/", { vehicle: "5", route: "4", driver: "2", conductor: "", starts_at: "2026-11-12T08:00", ends_at: "2026-11-12T17:00" }));
});

test("ending a shift assignment preserves its history and records the staff reason", async () => {
  const active = { id: 7, vehicle_registration: "KAA 123A", route_name: "Town Loop", driver_name: "Assigned Driver", starts_at: "2026-11-12T05:00:00Z", status: "active" };
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "transport/assignments/" ? [active] : resources[url] }));
  api.post.mockResolvedValue({ data: { ...active, ends_at: "2026-11-12T10:00:00Z", status: "ended" } });
  render(<MemoryRouter><TransportOperations /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "End assignment" }));
  const confirm = screen.getByRole("button", { name: "Confirm end" });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Reason for ending this assignment"), { target: { value: "Replacement crew arrived" } });
  fireEvent.click(confirm);
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/assignments/7/end/", { reason: "Replacement crew arrived" }));
  expect(await screen.findByText("Assignment ended for KAA 123A.")).toBeInTheDocument();
  expect(screen.getByText("Town Loop · Assigned Driver · No conductor")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "End assignment" })).not.toBeInTheDocument();
});
