import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TransportCrew from "./TransportCrew";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../hooks/useInactivityLogout", () => ({ useInactivityLogout: () => ({ showWarning: false, secondsLeft: 0, stayLoggedIn: jest.fn() }) }));

const activeShift = {
  assignment: {
    id: 8, vehicle_registration: "KAA 123A", route_name: "Town Loop", driver_name: "D. Driver", conductor_name: "",
    status: "active", starts_at: "2026-11-12T05:00:00Z", ends_at: null, collection_total: "0.00", collections: [], remittances: [],
  },
  message: "Collections are reported separately from confirmed remittances.",
};

beforeEach(() => {
  window.localStorage.clear(); window.sessionStorage.clear(); jest.clearAllMocks();
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true });
  useAuth.mockReturnValue({ user: { id: 23, username: "driver", transport_roles: ["driver"] }, loading: false, logout: jest.fn() });
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "transport/crew/history/" ? [] : activeShift }));
});

const crew = () => <MemoryRouter><TransportCrew /></MemoryRouter>;
function renderCrew() { return render(crew()); }

function record(amount, notes = "") {
  fireEvent.change(screen.getByLabelText("Amount (KES)"), { target: { value: amount } });
  fireEvent.change(screen.getByLabelText("Notes (optional)"), { target: { value: notes } });
  fireEvent.click(screen.getByRole("button", { name: "Record collection" }));
}

test("crew sees the server assignment and records a persisted collection", async () => {
  api.post.mockResolvedValue({ data: { id: 51, amount: "875.50", payment_status: "not_settled" } });
  renderCrew();
  expect(await screen.findByText("KAA 123A · Town Loop")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Amount (KES)"), { target: { value: "875.50" } });
  fireEvent.change(screen.getByLabelText("Notes (optional)"), { target: { value: "Morning fares" } });
  fireEvent.click(screen.getByRole("button", { name: "Record collection" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/crew/today/", expect.objectContaining({ assignment: 8, amount: "875.50", notes: "Morning fares" })));
  expect(await screen.findByText(/Collection recorded: KES 875.50/)).toBeInTheDocument();
  expect(api.get.mock.calls.filter(([url]) => url === "transport/crew/today/")).toHaveLength(2);
});

test("offline save is scoped to the signed-in user and uses clear waiting text", async () => {
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value: false });
  window.localStorage.setItem("transport-offline-collections:99", JSON.stringify([{ assignment: 8, amount: "999", notes: "other user", client_key: "private" }]));
  renderCrew();
  expect(await screen.findByText("KAA 123A · Town Loop")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Amount (KES)"), { target: { value: "120" } });
  fireEvent.click(screen.getByRole("button", { name: "Record collection" }));
  expect(await screen.findByText("Saved on this phone — waiting to sync. Retry when connected.")).toBeInTheDocument();
  expect(window.localStorage.getItem("transport-offline-collections:23")).toContain('"amount":"120"');
  expect(screen.queryByText(/other user/)).not.toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});

test("distinct offline collections preserve both payloads and are hidden when the signed-in user changes", async () => {
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value: false });
  const { rerender } = renderCrew();
  await screen.findByText("KAA 123A · Town Loop");
  record("120", "first collection");
  record("45", "second collection");
  const drafts = JSON.parse(window.localStorage.getItem("transport-offline-collections:23"));
  expect(drafts).toEqual([
    expect.objectContaining({ amount: "120", notes: "first collection" }),
    expect.objectContaining({ amount: "45", notes: "second collection" }),
  ]);
  expect(drafts[0].client_key).not.toBe(drafts[1].client_key);
  expect(drafts[0].client_key).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/);
  expect(screen.getAllByText("Saved on this phone — waiting to sync")).toHaveLength(2);

  useAuth.mockReturnValue({ user: { id: 99, username: "other-driver" }, loading: false, logout: jest.fn() });
  rerender(crew());
  await screen.findByText("KAA 123A · Town Loop");
  expect(screen.queryByText(/first collection/)).not.toBeInTheDocument();
  expect(screen.queryByText(/second collection/)).not.toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});

test("network retry keeps the same collection key and does not create duplicate local drafts", async () => {
  const networkError = new Error("connection dropped");
  api.post.mockRejectedValueOnce(networkError).mockResolvedValueOnce({ data: { id: 72, amount: "44.00", duplicate: true } });
  renderCrew();
  await screen.findByText("KAA 123A · Town Loop");
  fireEvent.change(screen.getByLabelText("Amount (KES)"), { target: { value: "44" } });
  fireEvent.click(screen.getByRole("button", { name: "Record collection" }));
  expect(await screen.findByText("Saved on this phone — waiting to sync. Retry when connected.")).toBeInTheDocument();
  const stored = JSON.parse(window.localStorage.getItem("transport-offline-collections:23"));
  fireEvent.click(screen.getByRole("button", { name: "Retry sync" }));
  await waitFor(() => expect(api.post).toHaveBeenLastCalledWith("transport/crew/today/", expect.objectContaining({ client_key: stored[0].client_key, recorded_by: 23 })));
  expect(await screen.findByText("This collection was already saved. No second record was created.")).toBeInTheDocument();
  expect(JSON.parse(window.localStorage.getItem("transport-offline-collections:23"))).toEqual([]);
});

test("a saved draft is retryable when today's assignment has ended", async () => {
  const draft = { assignment: 8, amount: "42.00", notes: "Past assignment", client_key: "af1957bd-836f-42a6-85d8-02e73e27e732" };
  window.localStorage.setItem("transport-offline-collections:23", JSON.stringify([draft]));
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "transport/crew/history/" ? [] : { assignment: null } }));
  api.post.mockResolvedValue({ data: { duplicate: true } });
  renderCrew();
  expect(await screen.findByText("No valid assignment for today")).toBeInTheDocument();
  expect(screen.getByLabelText("What needs checking?")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry sync" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/crew/today/", { ...draft, recorded_by: 23 }));
  expect(await screen.findByText("This collection was already saved. No second record was created.")).toBeInTheDocument();
});

test("an assignment load failure replaces loading instead of showing both states", async () => {
  api.get.mockRejectedValue(new Error("offline"));
  renderCrew();
  expect(await screen.findByText("Shift unavailable")).toBeInTheDocument();
  expect(screen.queryByText("Checking your current assignment…")).not.toBeInTheDocument();
});

test("a closed shift reports zero due or missing rules without allowing a payment", async () => {
  const closure = { reported_gross: "0.00", approved_expenses: "0.00", deductible_expenses: "0.00", calculation_status: "calculated", expected_remittance: "0.00" };
  const closed = { ...activeShift, assignment: { ...activeShift.assignment, shift_status: "closed", closure } };
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "transport/crew/history/" ? [] : closed }));
  const { unmount } = renderCrew();
  expect(await screen.findByText("No payment due for this shift.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Record collection" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Create remittance request" })).not.toBeInTheDocument();
  unmount();

  const needsRule = { ...closed, assignment: { ...closed.assignment, closure: { ...closure, calculation_status: "rule_required", expected_remittance: null, calculation_note: "No approved deduction policy." } } };
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "transport/crew/history/" ? [] : needsRule }));
  renderCrew();
  expect(await screen.findByText("Approved deduction rule required")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Create remittance request" })).not.toBeInTheDocument();
});

test("payment submits the server's available amount and displays pending cash without showing a receipt", async () => {
  const remittance = { id: "R1", payment_reference: "TR-123", amount: "100.00", received_amount: "0.00", outstanding_amount: "100.00", available_to_pay: "65.00", can_pay: true, status: "pending", payments: [{ id: 42, method: "cash", status: "pending", reported_amount: "35.00", received_amount: null }] };
  const shift = { ...activeShift, assignment: { ...activeShift.assignment, remittances: [remittance], shift_status: "closed" } };
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "transport/crew/history/" ? [] : shift }));
  api.post.mockResolvedValue({ data: { status: "pending" } });
  renderCrew();
  expect(await screen.findByText(/awaiting confirmation/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "View receipt" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Submit cash handover" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("transport/remittances/R1/cash/", expect.objectContaining({ amount: "65.00" })));
  expect(await screen.findByText(/A clerk must confirm receipt/)).toBeInTheDocument();
});
