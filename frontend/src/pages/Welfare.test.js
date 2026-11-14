import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import api from "../api/axios";
import Welfare from "./Welfare";

jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../components/Layout", () => ({ children }) => <>{children}</>);
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: { username: "testmember", first_name: "Test" } }),
}));
jest.mock("../components/ui/MetricCard", () => ({ label, value }) => (
  <div data-testid="metric">{label}: {value}</div>
));
jest.mock("../components/ui/Icon", () => () => null);
jest.mock("../components/ui/StatusBadge", () => ({ label, status }) => (
  <span data-testid="badge">{label || status}</span>
));

const dashboard = {
  total_contributions: "50.00",
  case_counts: { submitted: 1, needs_information: 0, under_review: 0, approved: 0, rejected: 0 },
  categories: [{ category: "medical", maximum_benefit: "5000.00", minimum_contributions: "0.00" }],
  active_policy_version: "v1",
};

const request = {
  id: 4, category: "medical", description: "Support for treatment",
  requested_amount: "500.00", status: "submitted", documents: [], created_at: "2026-11-01T08:00:00Z",
};

const contribution = {
  id: 9, amount: "50.00", posted_at: "2026-11-01T08:00:00Z", source_reference: "POSTED-9",
};

function mockGetAll(requests = [request]) {
  api.get.mockImplementation((url) => {
    if (url === "welfare/member-dashboard/") return Promise.resolve({ data: dashboard });
    if (url === "welfare/requests/") return Promise.resolve({ data: requests });
    if (url === "welfare/contributions/") return Promise.resolve({ data: [contribution] });
    return Promise.reject(new Error("unexpected url: " + url));
  });
}

beforeEach(() => { jest.resetAllMocks(); });

test("member dashboard loads contributions and case counts", async () => {
  mockGetAll([]);
  render(<Welfare />);
  expect(await screen.findByText(/Total contributions/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: /Contributions/ }));
  expect(await screen.findByText("POSTED-9")).toBeInTheDocument();
});

test("member submits a welfare request and it appears in the list", async () => {
  // First load: no requests yet
  api.get.mockImplementation((url) => {
    if (url === "welfare/member-dashboard/") return Promise.resolve({ data: dashboard });
    if (url === "welfare/requests/") return Promise.resolve({ data: [] });
    if (url === "welfare/contributions/") return Promise.resolve({ data: [] });
    return Promise.reject(new Error("unexpected url: " + url));
  });
  api.post.mockResolvedValueOnce({ data: request });

  render(<Welfare />);

  // Wait for initial load
  const newBtn = await screen.findByRole("button", { name: /New request/ });
  fireEvent.click(newBtn);

  // Fill form
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "medical" } });
  fireEvent.change(screen.getByLabelText("Requested amount (KES)"), { target: { value: "500.00" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Support for treatment" } });

  // After submit, reload will return the request
  api.get.mockImplementation((url) => {
    if (url === "welfare/member-dashboard/") return Promise.resolve({ data: dashboard });
    if (url === "welfare/requests/") return Promise.resolve({ data: [request] });
    if (url === "welfare/contributions/") return Promise.resolve({ data: [] });
    return Promise.reject(new Error("unexpected url: " + url));
  });

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /Submit request/ }));
  });

  await waitFor(() => {
    expect(api.post).toHaveBeenCalledWith("welfare/requests/", {
      category: "medical",
      description: "Support for treatment",
      requested_amount: "500.00",
    });
  });

  // The request now appears in My cases tab (as an h3 heading)
  const categoryHeadings = await screen.findAllByText("medical");
  expect(categoryHeadings.some((el) => el.tagName === "H3")).toBe(true);
});

test("supporting documents are submitted as authenticated multipart uploads", async () => {
  mockGetAll();
  api.post.mockResolvedValue({ data: { id: 12, name: "proof.pdf" } });
  render(<Welfare />);
  fireEvent.click(await screen.findByRole("button", { name: "Upload document" }));
  const file = new File(["%PDF"], "proof.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Supporting document"), { target: { files: [file] } });
  await waitFor(() => expect(api.post).toHaveBeenCalled());
  expect(api.post.mock.calls[0][0]).toBe("welfare/requests/4/documents/");
  expect(api.post.mock.calls[0][1].get("document")).toEqual(file);
  expect(await screen.findByText("Support for treatment")).toBeInTheDocument();
});
