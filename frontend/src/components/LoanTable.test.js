import React from "react";
import { render, screen } from "@testing-library/react";
import LoanTable from "./LoanTable";

jest.mock("./RepayLoanModal", () => function MockRepayLoanModal() { return null; });

test("loan table uses shared controls and labels recorded balances without claiming disbursement", () => {
  render(<LoanTable loans={[
    { id: 21, amount: "5000.00", interest: "10.00", repayment_months: 3, balance: "5500.00", status: "approved" },
  ]} />);
  expect(screen.getByRole("columnheader", { name: "Recorded balance" })).toBeInTheDocument();
  expect(screen.getAllByText("KES 5,500.00")).toHaveLength(2);
  expect(screen.getByText(/disbursement is not tracked here/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open repayment for loan 21" })).toHaveTextContent("Repay");
});
