import React from "react";
import "../styles/tables.css";

function TopSavers({ savers }) {
  const rows = savers || [];

  return (
    <>
      <h2 className="table-title">🏆 Top Savers</h2>

      <table className="data-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Member</th>
            <th>Total Savings</th>
          </tr>
        </thead>

        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan="3" style={{ textAlign: "center", color: "#94a3b8" }}>
                No savings found.
              </td>
            </tr>
          ) : (
            rows.map((saver, index) => (
              <tr key={index}>
                <td>
                  <span style={{
                    fontWeight: "700",
                    color: index === 0 ? "#f59e0b" : index === 1 ? "#94a3b8" : index === 2 ? "#b45309" : "#64748b"
                  }}>
                    {index === 0 ? "🥇" : index === 1 ? "🥈" : index === 2 ? "🥉" : `#${index + 1}`}
                  </span>
                </td>
                {/* backend sends { username, total } */}
                <td>{saver.username || saver.member || "—"}</td>
                <td>KES {Number(saver.total ?? saver.total_savings ?? 0).toLocaleString()}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </>
  );
}

export default TopSavers;
