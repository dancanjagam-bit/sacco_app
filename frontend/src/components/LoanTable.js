import React, { useState } from "react";
import "../styles/tables.css";
import DataTable from "./ui/DataTable";
import Button from "./ui/Button";
import StatusBadge from "./ui/StatusBadge";
import RepayLoanModal from "./RepayLoanModal";

const money = (value) => {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const amount = Number(value);
  return Number.isFinite(amount) ? `KES ${amount.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "Unavailable";
};
const numericValue = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export default function LoanTable({ loans = [], onUpdated }) {
  const [selectedLoan, setSelectedLoan] = useState(null);
  const rows = Array.isArray(loans) ? loans : [];

  return (
    <section aria-labelledby="my-loans-title" className="loan-table-section">
      <h2 className="table-title" id="my-loans-title">My loans</h2>
      <p className="ui-muted">Recorded loan balances are shown below. The current loan records do not establish that approved funds were sent.</p>
      <p className="ui-muted">Loan disbursement is not tracked here as a separate confirmed status.</p>
      <DataTable label="Member loan history">
        <table className="ui-table">
          <thead><tr><th>ID</th><th>Principal</th><th>Interest</th><th>Total payable</th><th>Recorded balance</th><th>Monthly payment</th><th>Period</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            {rows.length === 0 ? <tr><td colSpan="9" className="ui-empty">No loans found.</td></tr> : rows.map((loan) => {
              const amount = numericValue(loan.amount);
              const rate = numericValue(loan.interest);
              const months = numericValue(loan.repayment_months);
              const totalPayable = amount !== null && rate !== null ? amount + amount * rate / 100 : null;
              const monthly = totalPayable !== null && months > 0 ? totalPayable / months : null;
              return <tr key={loan.id}>
                <td>#{loan.id}</td>
                <td>{money(amount)}</td>
                <td>{rate !== null ? `${rate}%` : "Unavailable"}</td>
                <td>{totalPayable !== null ? money(totalPayable) : "Unavailable"}</td>
                <td>{loan.balance === null || loan.balance === undefined ? "Unavailable" : money(loan.balance)}</td>
                <td>{monthly !== null ? money(monthly) : "Unavailable"}</td>
                <td>{months !== null && months > 0 ? `${months} months` : "Unavailable"}</td>
                <td><StatusBadge status={loan.status} /></td>
                <td>{loan.status === "approved" ? <Button variant="accent" size="sm" aria-label={`Open repayment for loan ${loan.id}`} onClick={() => setSelectedLoan(loan)}>Repay</Button> : "—"}</td>
              </tr>;
            })}
          </tbody>
        </table>
      </DataTable>
      {selectedLoan && <RepayLoanModal loan={selectedLoan} onClose={() => setSelectedLoan(null)} onUpdated={() => { onUpdated?.(); }} />}
    </section>
  );
}
