import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

function MonthlyChart({ title, data, color = "#2563eb" }) {
  const chartData = Array.isArray(data) ? data : [];

  return (
    <>
      <h3 style={{ marginBottom: "16px", fontSize: "15px", fontWeight: "700", color: "#1e293b" }}>
        {title}
      </h3>

      {chartData.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px 0", color: "#94a3b8", fontSize: "14px" }}>
          No data yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              formatter={(value) => [`KES ${Number(value).toLocaleString()}`, "Amount"]}
              contentStyle={{ borderRadius: "8px", border: "1px solid #e2e8f0", fontSize: "13px" }}
            />
            <Bar dataKey="total" fill={color} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </>
  );
}

export default MonthlyChart;
