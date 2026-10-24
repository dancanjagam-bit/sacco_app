import React from "react";
import "../styles/tables.css";

function RecentActivity({ transactions }) {
  const rows = transactions || [];

  return (
    <>
      <h2 className="table-title">Recent Activity</h2>

      <table className="data-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Member</th>
            <th>Type</th>
            <th>Amount</th>
          </tr>
        </thead>

        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan="4" style={{ textAlign: "center", color: "#94a3b8" }}>
                No recent activity.
              </td>
            </tr>
          ) : (
            rows.map((t) => (
              <tr key={t.id}>
                <td>
                  {t.created_at
                    ? new Date(t.created_at).toLocaleDateString("en-KE")
                    : "—"}
                </td>
                <td>{t.member || "—"}</td>
                <td style={{ textTransform: "capitalize" }}>
                  <span className={`status status-${
                    t.type === "deposit"   ? "approved" :
                    t.type === "repayment" ? "info"     : "pending"
                  }`}>
                    {t.type}
                  </span>
                </td>
                <td>KES {Number(t.amount).toLocaleString()}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </>
  );
}

export default RecentActivity;
