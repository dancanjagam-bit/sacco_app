import React from "react";
import { render, screen } from "@testing-library/react";
import AccountCard from "./AccountCard";
import DataTable from "./DataTable";
import FormField from "./FormField";

test("account card keeps its primary figure distinct from supporting balances", () => {
  render(<AccountCard
    label="Available FOSA"
    value="KES 300.00"
    details={[
      { label: "Recorded FOSA balance", value: "KES 400.00" },
      { label: "Held for withdrawals", value: "KES 100.00" },
    ]}
  />);
  const card = screen.getByRole("region", { name: "Available FOSA" });
  expect(card).toHaveTextContent("KES 300.00");
  expect(card).toHaveTextContent("Recorded FOSA balanceKES 400.00");
  expect(card).toHaveTextContent("Held for withdrawalsKES 100.00");
});

test("account card presents unknown values without converting them to zero", () => {
  render(<AccountCard label="Available FOSA" value={null} loading={false} />);
  expect(screen.getByRole("region", { name: "Available FOSA" })).toHaveTextContent("Unavailable");
  expect(screen.queryByText("KES 0.00")).not.toBeInTheDocument();
});

test("form field connects visible label, hint, and validation error to its control", () => {
  render(<FormField label="Amount (KES)" htmlFor="amount" hint="Whole KES only" error="Enter a valid amount.">
    <input id="amount" />
  </FormField>);
  const input = screen.getByLabelText("Amount (KES)");
  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(input).toHaveAccessibleDescription("Whole KES only Enter a valid amount.");
});

test("data table container has a scrollable accessible region label", () => {
  render(<DataTable label="Transaction history"><table><tbody><tr><td>Entry</td></tr></tbody></table></DataTable>);
  expect(screen.getByRole("region", { name: "Transaction history" })).toHaveTextContent("Entry");
});
