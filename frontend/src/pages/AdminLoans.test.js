import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AdminLoans from "./AdminLoans";
import api from "../api/axios";

jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../components/Layout", () => ({ children }) => <div>{typeof children === "function" ? children() : children}</div>);

const assignedLoan = {
  id: 41, member: "Synthetic applicant", member_number: "SYN-41", amount: 5000,
  interest: 10, repayment_months: 6, total_savings_at_application: 1000,
  savings_months: 6, status: "pending", created_at: "2026-01-01T12:00:00Z",
  can_appraise: true, can_decide: false,
};

beforeEach(() => jest.clearAllMocks());

test("credit reviewer can open guarantors only through the assigned review endpoint", async () => {
  api.get.mockImplementation((url) => {
    if (url === "admin/loans/") return Promise.resolve({ data: [assignedLoan] });
    if (url === "admin/loan/41/guarantors/") return Promise.resolve({ data: [] });
    return Promise.reject(new Error("Unexpected endpoint"));
  });
  render(<AdminLoans />);
  fireEvent.click(await screen.findByRole("button", { name: "Review guarantors" }));
  expect(await screen.findByText("No guarantor requests are recorded for this loan.")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith("admin/loan/41/guarantors/");
  expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
});

test("a removed assignment error is visible and retryable", async () => {
  api.get.mockResolvedValueOnce({ data: [assignedLoan] })
    .mockRejectedValueOnce({ response: { data: { detail: "This loan is not assigned for appraisal to your account." } } })
    .mockResolvedValueOnce({ data: [] });
  render(<AdminLoans />);
  fireEvent.click(await screen.findByRole("button", { name: "Review guarantors" }));
  expect(await screen.findByText("This loan is not assigned for appraisal to your account.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(api.get).toHaveBeenLastCalledWith("admin/loan/41/guarantors/"));
  expect(await screen.findByText("No guarantor requests are recorded for this loan.")).toBeInTheDocument();
});
