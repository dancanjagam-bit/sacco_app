import React from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from "recharts";

const COLORS = {
  pending:  "#f59e0b",
  approved: "#2563eb",
  repaid:   "#16a34a",
  rejected: "#dc2626",
};

function LoanStatusChart({ data }) {
  // data arrives as { pending: 2, approved: 1, repaid: 0, rejected: 0 }
  // Convert to array recharts can use
  const chartData = Object.entries(data || {})
    .map(([status, total]) => ({ status, total }))
    .filter((entry) => entry.total > 0);

  if (chartData.length === 0) {
    return (
      <>
        <h3 style={{ marginBottom: "20px" }}>Loan Status Distribution</h3>
        <div style={{ textAlign: "center", padding: "60px 0", color: "#94a3b8" }}>
          No loan data yet
        </div>
      </>
    );
  }

  return (
    <>
      <h3 style={{ marginBottom: "20px" }}>Loan Status Distribution</h3>

      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={chartData}
            dataKey="total"
            nameKey="status"
            outerRadius={110}
            label={({ status, total }) => `${status}: ${total}`}
          >
            {chartData.map((entry) => (
              <Cell
                key={entry.status}
                fill={COLORS[entry.status] || "#94a3b8"}
              />
            ))}
          </Pie>
          <Tooltip formatter={(value, name) => [value, name]} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </>
  );
}

export default LoanStatusChart;
