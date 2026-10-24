import React from "react";
import "../styles/cards.css";

function DashboardCards({ data }) {
  const cards = [
    {
      title: "Total Savings",
      value: `KES ${Number(data.total_savings || 0).toLocaleString()}`,
      icon: "💰",
      color: "#22c55e",
    },
    {
      title: "Total Loans",
      value: data.total_loans,
      icon: "🏦",
      color: "#2563eb",
    },
    {
      title: "Pending Loans",
      value: data.pending_loans,
      icon: "⏳",
      color: "#f59e0b",
    },
    {
      title: "Approved Loans",
      value: data.approved_loans,
      icon: "✅",
      color: "#8b5cf6",
    },
  ];

  return (
    <div className="cards-grid">
      {cards.map((card, index) => (
        <div
          key={index}
          className="dashboard-card"
          style={{
            borderLeft: `6px solid ${card.color}`,
          }}
        >
          <div className="card-icon">
            {card.icon}
          </div>

          <h4 className="card-title">
            {card.title}
          </h4>

          <h2 className="card-value">
            {card.value}
          </h2>
        </div>
      ))}
    </div>
  );
}

export default DashboardCards;
