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

function MonthlyChart({ title = "Monthly amounts", data, color = "var(--chart-primary)" }) {
  const chartData = (Array.isArray(data) ? data : []).filter((entry) =>
    entry && typeof entry.month === "string" && entry.month.trim() &&
    entry.total != null && Number.isFinite(Number(entry.total))
  );
  const description = chartData.length
    ? `${chartData.length} months. ${chartData.map((entry) => `${entry.month}: KES ${Number(entry.total).toLocaleString("en-KE", { maximumFractionDigits: 2 })}`).join("; ")}.`
    : "No chart data available.";

  return (
    <div className="monthly-chart" role="img" aria-label={`${title}. ${description}`}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={chartData} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 12, fill: "var(--text-muted)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={12}
          />
          <YAxis
            width={58}
            tick={{ fontSize: 12, fill: "var(--text-muted)" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value) => `${(Number(value) / 1000).toLocaleString("en-KE", { maximumFractionDigits: 1 })}k`}
          />
          <Tooltip
            formatter={(value) => [`KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, "Recorded savings"]}
            contentStyle={{ borderRadius: "10px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "14px" }}
          />
          <Bar dataKey="total" fill={color} radius={[5, 5, 0, 0]} maxBarSize={42} />
        </BarChart>
      </ResponsiveContainer>
      <span className="sr-only">{description}</span>
    </div>
  );
}

export default MonthlyChart;
