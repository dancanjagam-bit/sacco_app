import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";

import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import "../styles/auth.css";

function Login() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [message,  setMessage]  = useState("");
  const [loading,  setLoading]  = useState(false);
  const [attempts,  setAttempts] = useState(0);

  // Restore remembered username
  useEffect(() => {
    const saved = localStorage.getItem("sacco_remember_username");
    if (saved) {
      setUsername(saved);
      setRememberMe(true);
    }
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      const tokenRes = await api.post("token/", { username, password });
      localStorage.setItem("access",  tokenRes.data.access);
      localStorage.setItem("refresh", tokenRes.data.refresh);

      // Remember username if checked
      if (rememberMe) {
        localStorage.setItem("sacco_remember_username", username);
      } else {
        localStorage.removeItem("sacco_remember_username");
      }

      await refreshUser();

      const dashRes = await api.get("dashboard/");
      const u = dashRes.data;

      if (u.is_staff || u.is_superuser) {
        navigate("/admin/dashboard", { replace: true });
      } else {
        navigate("/dashboard", { replace: true });
      }
    } catch (err) {
      setAttempts(prev => prev + 1);
      if (err.response?.status === 401 || err.response?.status === 400) {
        const msgs = [
          "Invalid username or password.",
          "Incorrect credentials. Please try again.",
          "Login failed. Check your username and password.",
        ];
        setMessage(msgs[Math.min(attempts, msgs.length - 1)]);
      } else if (err.response?.status === 429) {
        setMessage("Too many login attempts. Please wait a moment and try again.");
      } else if (err.code === "ERR_NETWORK") {
        setMessage("Cannot connect to server. Please check your internet connection.");
      } else {
        setMessage("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        {/* Brand header */}
        <div className="auth-brand">
          <div className="auth-logo">🏦</div>
          <h1 className="auth-title">SACCO Management System</h1>
          <p className="auth-subtitle">Sign in to your account</p>
        </div>

        <form className="auth-form" onSubmit={handleLogin} autoComplete="on">
          {/* Username */}
          <div className="auth-field">
            <label htmlFor="username">Username</label>
            <div className="auth-input-wrap">
              <span className="auth-input-icon">👤</span>
              <input
                id="username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                autoComplete="username"
                className="auth-input-with-icon"
              />
            </div>
          </div>

          {/* Password with toggle */}
          <div className="auth-field">
            <label htmlFor="password">Password</label>
            <div className="auth-input-wrap">
              <span className="auth-input-icon">🔒</span>
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="auth-input-with-icon"
                style={{ paddingRight: "48px" }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="auth-toggle-pw"
                tabIndex={-1}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "🙈" : "👁️"}
              </button>
            </div>
          </div>

          {/* Remember me + forgot password */}
          <div className="auth-options">
            <label className="auth-checkbox">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              <span>Remember me</span>
            </label>
            <Link to="/forgot-password" className="auth-forgot-link">
              Forgot password?
            </Link>
          </div>

          {/* Submit */}
          <button className="auth-button" type="submit" disabled={loading}>
            {loading ? (
              <>
                <span className="auth-spinner" />
                Signing in...
              </>
            ) : (
              "Sign In →"
            )}
          </button>
        </form>

        {/* Error message */}
        {message && (
          <div className="auth-message error">
            ⚠️ {message}
          </div>
        )}

        {/* Security notice */}
        <div className="auth-security-notice">
          🔐 Your connection is encrypted. Never share your password with anyone.
        </div>

        {/* Register link */}
        <div className="auth-footer">
          Don't have an account?{" "}
          <Link to="/register">Register here</Link>
        </div>
      </div>

      {/* Footer */}
      <div className="auth-page-footer">
        © {new Date().getFullYear()} SACCO Management System · Built for Kenya
      </div>
    </div>
  );
}

export default Login;
