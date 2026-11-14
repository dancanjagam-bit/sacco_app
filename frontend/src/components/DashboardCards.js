import React from "react";
import MetricCard from "./ui/MetricCard";

function amount(value) {
  if (value == null || !Number.isFinite(Number(value))) return "Unavailable";
  return `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function count(value) {
  if (value == null || !Number.isFinite(Number(value))) return "Unavailable";
  return Number(value).toLocaleString("en-KE");
}

function DashboardCards({ data }) {
  const cards = [
    {
      label: "Total savings recorded",
      value: amount(data?.total_savings),
      helper: "Recorded savings entries",
      icon: "coins",
    },
    {
      label: "Total loans",
      value: count(data?.total_loans),
      helper: "Loan records in the response",
      icon: "bank",
    },
    {
      label: "Pending loans",
      value: count(data?.pending_loans),
      helper: "Awaiting a recorded decision",
      icon: "clock",
      tone: "amber",
    },
    {
      label: "Approved loans",
      value: count(data?.approved_loans),
      helper: "Approval does not confirm disbursement",
      icon: "file",
    },
  ];

  return (
    <div className="bento-grid staff-kpi-grid">
      {cards.map((card) => (
        <MetricCard key={card.label} {...card} />
      ))}
    </div>
  );
}

export default DashboardCards;
