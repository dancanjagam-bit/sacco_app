import React, { useEffect, useState } from "react";
import api from "../api/axios";

import Layout from "../components/Layout";
import MonthlyChart from "../components/MonthlyChart";
import LoanStatusChart from "../components/LoanStatusChart";
import RecentActivity from "../components/RecentActivity";
import TopSavers from "../components/TopSavers";

import "../styles/dashboard.css";
import "../styles/adminDashboard.css";

function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDashboard();
  }, []);

  const fetchDashboard = async () => {
    setError(null);
    try {
      const res = await api.get("admin/dashboard/");
      setStats(res.data);
    } catch (err) {
      console.error(err);
      setError("Failed to load dashboard data. Please refresh.");
    }
  };

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">Admin Dashboard</h2>

          {/* Error state */}
          {error && (
            <div style={{ color: "#dc3545", marginBottom: "16px" }}>
              ⚠️ {error}
              <button
                onClick={fetchDashboard}
                style={{ marginLeft: "12px" }}
              >
                Retry
              </button>
            </div>
          )}

          {/* Loading state */}
          {!stats && !error && (
            <p style={{ color: "#6b7280" }}>Loading dashboard...</p>
          )}

          {/* Loaded state */}
          {stats && (
            <>
              {/* Summary cards */}
              <div className="summary-grid">
                <div className="summary-card">
                  <h4>👥 Total Members</h4>
                  <h2>{stats.total_members}</h2>
                </div>
                <div className="summary-card">
                  <h4>💰 Total Savings</h4>
                  <h2>KES {Number(stats.total_savings).toLocaleString()}</h2>
                </div>
                <div className="summary-card">
                  <h4>🏦 Active Loan Book</h4>
                  <h2>KES {Number(stats.active_loans).toLocaleString()}</h2>
                </div>
                <div className="summary-card">
                  <h4>⏳ Pending Loans</h4>
                  <h2>{stats.pending_loans}</h2>
                </div>
                <div className="summary-card">
                  <h4>✅ Approved Loans</h4>
                  <h2>{stats.approved_loans}</h2>
                </div>
                <div className="summary-card">
                  <h4>🔄 Repaid Loans</h4>
                  <h2>{stats.repaid_loans}</h2>
                </div>
                <div className="summary-card">
                  <h4>📈 Interest Earned</h4>
                  <h2>KES {Number(stats.interest_earned).toLocaleString()}</h2>
                </div>
              </div>

              {/* Charts row 1 */}
              <div className="dashboard-row">
                <div className="dashboard-half">
                  <MonthlyChart
                    title="Monthly Savings"
                    data={stats.monthly_savings}
                  />
                </div>
                <div className="dashboard-half">
                  <LoanStatusChart data={stats.loan_status} />
                </div>
              </div>

              {/* Charts row 2 */}
              <div className="dashboard-row">
                <div className="dashboard-half">
                  <MonthlyChart
                    title="Monthly Loans Disbursed"
                    data={stats.monthly_loans}
                  />
                </div>
                <div className="dashboard-half">
                  <MonthlyChart
                    title="Monthly Repayments"
                    data={stats.monthly_repayments}
                  />
                </div>
              </div>

              {/* Tables */}
              <div className="dashboard-row">
                <div className="dashboard-half">
                  <RecentActivity transactions={stats.recent_transactions} />
                </div>
                <div className="dashboard-half">
                  <TopSavers savers={stats.top_savers} />
                </div>
              </div>
            </>
          )}
        </>
      )}
    </Layout>
  );
}

export default AdminDashboard;
