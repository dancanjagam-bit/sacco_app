import React, { useState } from "react";
import "../styles/tables.css";
import RepayLoanModal from "./RepayLoanModal";

function LoanTable({ loans, onUpdated }) {
  const [selectedLoan, setSelectedLoan] = useState(null);

  const getStatusClass = (status) => {
    switch (status.toLowerCase()) {
      case "approved":
        return "status status-approved";

      case "pending":
        return "status status-pending";

      case "rejected":
        return "status status-rejected";

      case "repaid":
        return "status status-approved";

      default:
        return "status";
    }
  };

  return (
    <>
      <h2 className="table-title">My Loans</h2>

      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Amount</th>
            <th>Interest</th>
            <th>Total Payable</th>
            <th>Remaining</th>
            <th>Monthly Payment</th>
            <th>Period</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>

        <tbody>
          {loans.length === 0 ? (
            <tr>
              <td colSpan="9">No loans found.</td>
            </tr>
          ) : (
            loans.map((loan) => {
              const amount = Number(loan.amount);
              const interest = Number(loan.interest);

              const interestAmount =
                (amount * interest) / 100;

              const totalPayable =
                amount + interestAmount;

              const remaining =
                Number(loan.balance);

              const monthlyPayment =
                totalPayable / loan.repayment_months;

              return (
                <tr key={loan.id}>
                  <td>{loan.id}</td>

                  <td>
                    KES {amount.toLocaleString()}
                  </td>

                  <td>
                    KES {interestAmount.toLocaleString()}
                  </td>

                  <td>
                    KES {totalPayable.toLocaleString()}
                  </td>

                  <td>
                    KES {remaining.toLocaleString()}
                  </td>

                  <td>
                    KES {monthlyPayment.toFixed(2)}
                  </td>

                  <td>
                    {loan.repayment_months} Months
                  </td>

                  <td>
                    <span className={getStatusClass(loan.status)}>
                      {loan.status}
                    </span>
                  </td>

                  <td>
                    {loan.status === "approved" ? (
                      <button
                        onClick={() => setSelectedLoan(loan)}
                      >
                        Repay
                      </button>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      {selectedLoan && (
        <RepayLoanModal
          loan={selectedLoan}
          onClose={() => setSelectedLoan(null)}
          onUpdated={onUpdated}
        />
      )}
    </>
  );
}

export default LoanTable;
