import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import "../styles/auth.css";

function Login() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message,  setMessage]  = useState("");
  const [loading,  setLoading]  = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      const tokenRes = await api.post("token/", { username, password });
      localStorage.setItem("access",  tokenRes.data.access);
      localStorage.setItem("refresh", tokenRes.data.refresh);

      await refreshUser();

      // Read role from dashboard to decide where to go
      const dashRes = await api.get("dashboard/");
      const u = dashRes.data;

      if (u.is_staff || u.is_superuser) {
        navigate("/admin/dashboard", { replace: true });
      } else {
        navigate("/dashboard", { replace: true });
      }
    } catch (err) {
      if (err.response?.status === 401 || err.response?.status === 400) {
        setMessage("Invalid username or password.");
      } else {
        setMessage("Unable to connect. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🏦</div>
        <h1 className="auth-title">Welcome Back</h1>
        <p className="auth-subtitle">Sign in to your SACCO account</p>

        <form className="auth-form" onSubmit={handleLogin}>
          <div>
            <label>Username</label>
            <input
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div>
            <label>Password</label>
            <input
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button className="auth-button" type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign In →"}
          </button>
        </form>

        {message && (
          <p className="auth-message error">{message}</p>
        )}

        <div className="auth-footer">
          Don't have an account?{" "}
          <Link to="/register">Register here</Link>
          <br />
          <Link to="/forgot-password" style={{ color: "#64748b", fontSize: "13px" }}>
            Forgot your password?
          </Link>
        </div>
      </div>
    </div>
  );
}

export default Login;
