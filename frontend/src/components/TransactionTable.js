import React from "react";
import "../styles/tables.css";

function TransactionTable({ transactions }) {
  const getTypeClass = (type) => {
    switch (type.toLowerCase()) {
      case "deposit":
        return "status status-approved";

      case "loan":
        return "status status-pending";

      case "repayment":
        return "status status-info";

      default:
        return "status";
    }
  };
  return (
    <>
      <h2 className="table-title">Transaction History</h2>

      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Date</th>
            <th>Type</th>
            <th>Amount</th>
          </tr>
        </thead>

        <tbody>
          {transactions.length === 0 ? (
            <tr>
              <td colSpan="4">No transactions found.</td>
            </tr>
          ) : (
            transactions.map((transaction) => (
               <tr key={transaction.id}>
               <td>{transaction.id}</td>

               <td>
                {new Date(transaction.created_at).toLocaleDateString("en-KE")}
               </td>

               <td>
                 <span className={getTypeClass(transaction.type)}>
                   {transaction.type.charAt(0).toUpperCase() + transaction.type.slice(1)}
                 </span>
               </td>

               <td>KES {Number(transaction.amount).toLocaleString("en-KE")}</td>
             </tr>
            ))
          )}
        </tbody>
      </table>
    </>
  );
}

export default TransactionTable;
