import React from "react";

import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

import DashboardCards from "../components/DashboardCards";

import "../styles/dashboard.css";

function Dashboard() {
  const { user } = useAuth();

  return (
    <Layout>
      {() => (
        <>
          <DashboardCards data={user} />

          <h2 className="section-title">
            Dashboard Overview
          </h2>

          <p>
            Welcome back, <strong>{user.username}</strong>.
          </p>

          <p>
            Use the navigation menu on the left to manage your
            savings, loans, transactions and reports.
          </p>
        </>
      )}
    </Layout>
  );
}

export default Dashboard;
