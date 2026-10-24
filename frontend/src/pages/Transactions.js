import React, { useState } from "react";

import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import TransactionTable from "../components/TransactionTable";
import api from "../api/axios";

import "../styles/dashboard.css";

function Transactions() {
  const { user } = useAuth();

  const [filter, setFilter] = useState("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [search, setSearch] = useState("");
  const [exporting, setExporting] = useState(false);

  // Guard: transactions may not be loaded yet
  const transactions = user?.transactions || [];

  const totalDeposits = transactions
    .filter((t) => t.type === "deposit")
    .reduce((sum, t) => sum + Number(t.amount), 0);

  const totalLoans = transactions
    .filter((t) => t.type === "loan")
    .reduce((sum, t) => sum + Number(t.amount), 0);

  const totalRepayments = transactions
    .filter((t) => t.type === "repayment")
    .reduce((sum, t) => sum + Number(t.amount), 0);

  const filteredTransactions = transactions.filter((t) => {
    const txDate = new Date(t.created_at);

    const matchesType = filter === "all" || t.type === filter;

    const matchesStart =
      !startDate || txDate >= new Date(startDate);

    const matchesEnd =
      !endDate || txDate <= new Date(endDate + "T23:59:59");

    const matchesSearch =
      t.type.toLowerCase().includes(search.toLowerCase()) ||
      t.amount.toString().includes(search);

    return matchesType && matchesStart && matchesEnd && matchesSearch;
  });

  const exportExcel = async () => {
    setExporting(true);
    try {
      const response = await api.get("transactions/excel/", {
        responseType: "blob",
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = "transactions.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("Export failed.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">Transactions</h2>

          {/* Summary cards */}
          <div className="summary-grid">
            <div className="summary-card">
              <h4>Total Deposits</h4>
              <h2>KES {totalDeposits.toLocaleString()}</h2>
            </div>
            <div className="summary-card">
              <h4>Total Loans</h4>
              <h2>KES {totalLoans.toLocaleString()}</h2>
            </div>
            <div className="summary-card">
              <h4>Total Repayments</h4>
              <h2>KES {totalRepayments.toLocaleString()}</h2>
            </div>
            <div className="summary-card">
              <h4>Transactions</h4>
              <h2>{transactions.length}</h2>
            </div>
          </div>

          {/* Filters */}
          <div style={{ marginBottom: "16px" }}>
            <label><strong>Filter by type:</strong></label>
            <select
              className="amount-input"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              style={{ marginLeft: "10px" }}
            >
              <option value="all">All Transactions</option>
              <option value="deposit">Deposits</option>
              <option value="loan">Loans</option>
              <option value="repayment">Repayments</option>
            </select>
          </div>

          <div style={{ display: "flex", gap: "20px", marginBottom: "16px", flexWrap: "wrap", alignItems: "flex-end" }}>
            <div>
              <label>From</label>
              <br />
              <input
                type="date"
                className="amount-input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div>
              <label>To</label>
              <br />
              <input
                type="date"
                className="amount-input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
            <div>
              <label>Search</label>
              <br />
              <input
                type="text"
                className="amount-input"
                placeholder="Amount or type..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ width: "220px" }}
              />
            </div>
          </div>

          <div className="action-buttons" style={{ marginBottom: "16px" }}>
            <button onClick={exportExcel} disabled={exporting}>
              {exporting ? "Exporting..." : "📊 Export to Excel"}
            </button>
          </div>

          <TransactionTable transactions={filteredTransactions} />
        </>
      )}
    </Layout>
  );
}

export default Transactions;
