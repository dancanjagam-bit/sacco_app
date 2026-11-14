import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import api from "../api/axios";
import LoanCalculator from "./LoanCalculator";
import Loans from "./Loans";
import { ROUTES } from "../navigation/routes";

jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../components/Layout", () => ({ children }) => typeof children === "function" ? children() : children);
jest.mock("../components/LoanTable", () => () => null);
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ user: { loans: [] } }) }));

test("a server estimate prefills the actual loan application without submitting it", async () => {
  api.get.mockImplementation((url) => Promise.resolve({ data: {
    "loan/products/": { products: [{ id: "savings_tier", name: "Savings-tier loan", minimum_amount: "1.00", repayment_periods: [6, 12] }] },
    "loan/eligibility/": { eligible: true, max_loan: "10000.00", interest_band: "Bronze", interest_rates: { 6: { Bronze: 6 }, 12: { Bronze: 12 } } },
    "guarantor/pending/": [],
  }[url] }));
  api.post.mockResolvedValue({ data: { product: "savings_tier", amount: "850.50", repayment_months: 12,
    interest_rate: "12.00", fees: "0.00", estimated_installment: "79.38", total_interest: "102.06", total_repayment: "952.56",
    schedule: [{ month: 1, principal: "70.88", interest: "8.50", payment: "79.38", remaining: "873.18" }],
  } });
  render(<MemoryRouter initialEntries={[ROUTES.loanCalculator]}><Routes>
    <Route path={ROUTES.loanCalculator} element={<LoanCalculator />} />
    <Route path={ROUTES.loans} element={<Loans />} />
  </Routes></MemoryRouter>);
  fireEvent.change(await screen.findByLabelText("Requested amount (KES)"), { target: { value: "850.50" } });
  fireEvent.change(screen.getByLabelText("Repayment period"), { target: { value: "12" } });
  fireEvent.click(screen.getByRole("button", { name: "Calculate estimate" }));
  expect(await screen.findByRole("heading", { name: "Estimated repayments" })).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("loan/estimate/", { product: "savings_tier", amount: "850.50", repayment_months: 12 });
  fireEvent.click(screen.getByRole("button", { name: "Continue to application" }));
  expect(await screen.findByLabelText(/Loan Amount \(KES\)/)).toHaveValue(850.5);
  expect(screen.getByLabelText("Repayment Period")).toHaveValue("12");
  expect(screen.getByText("Loan product: Savings-tier loan")).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledTimes(1);
});
