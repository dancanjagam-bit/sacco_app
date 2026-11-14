import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";

import { authApi } from "../api/axios";
import { useAuth } from "../context/AuthContext";
import { portalDestination } from "../auth/portalDestination";
import { useSacco } from "../context/SaccoContext";
import PublicNavigation from "../components/PublicNavigation";
import SaccoLogo from "../components/SaccoLogo";
import Icon from "../components/ui/Icon";
import "../styles/auth.css";

function Login() {
  const navigate = useNavigate();
  const { user, loading: authLoading, refreshUser } = useAuth();
  const sacco = useSacco();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [resending, setResending] = useState(false);
  const [resendSeconds, setResendSeconds] = useState(0);

  // 2FA state
  const [twoFaMode, setTwoFaMode] = useState(false);
  const [twoFaInfo, setTwoFaInfo] = useState(null);
  const [otp, setOtp] = useState("");

  useEffect(() => {
    const saved = localStorage.getItem("sacco_remember_username");
    if (saved) {
      setUsername(saved);
      setRememberMe(true);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && user) navigate(portalDestination(user), { replace: true });
  }, [authLoading, user, navigate]);

  useEffect(() => {
    if (!twoFaMode || resendSeconds <= 0) return undefined;
    const timer = window.setTimeout(() => {
      setResendSeconds((remaining) => Math.max(0, remaining - 1));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [twoFaMode, resendSeconds]);

  const enterTwoFactor = (challenge) => {
    setTwoFaInfo(challenge);
    setTwoFaMode(true);
    setOtp("");
    setMessage("");
    const cooldown = Number(challenge.resend_after_seconds);
    setResendSeconds(Number.isFinite(cooldown) ? Math.max(0, cooldown) : 60);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      const res = await authApi.post("token/", { username, password });

      if (res.data.requires_2fa) {
        enterTwoFactor(res.data);
        setLoading(false);
        return;
      }

      await storeTokensAndNavigate(res.data);
    } catch (err) {
      handleLoginError(err);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2FA = async (e) => {
    e.preventDefault();
    setMessage("");
    setLoading(true);
    try {
      const res = await authApi.post("login/2fa/", {
        identifier: twoFaInfo.identifier,
        code: otp,
      });
      await storeTokensAndNavigate(res.data);
    } catch (err) {
      const data = err.response?.data;
      if (err.response?.status === 429) {
        setResendSeconds(Math.max(1, Number(data?.retry_after) || 60));
        setMessage("Too many verification attempts. Wait before trying again.");
      } else if (err.code === "ERR_NETWORK") {
        setMessage("The SACCO server could not verify the code. Check your connection and try again.");
      } else {
        setMessage(data?.error || "We could not verify that code. Check it or request a new one.");
      }
      setOtp("");
    } finally {
      setLoading(false);
    }
  };

  const handleResend2FA = async () => {
    if (!twoFaInfo?.challenge_token || resendSeconds > 0 || loading || resending) return;
    setMessage("");
    setResending(true);
    try {
      const response = await authApi.post("login/2fa/resend/", {
        identifier: twoFaInfo.identifier,
        challenge_token: twoFaInfo.challenge_token,
      });
      enterTwoFactor(response.data);
    } catch (err) {
      const data = err.response?.data;
      if (err.response?.status === 429) {
        setResendSeconds(Math.max(1, Number(data?.retry_after) || 60));
        setMessage("Please wait before requesting another verification code.");
      } else if (err.code === "ERR_NETWORK") {
        setMessage("The SACCO server could not process the retry. Check your connection and try again.");
      } else {
        setMessage(data?.detail || "We could not request another code. Return to sign in and try again.");
      }
    } finally {
      setResending(false);
    }
  };

  const backToSignIn = () => {
    setTwoFaMode(false);
    setTwoFaInfo(null);
    setOtp("");
    setResendSeconds(0);
    setMessage("");
  };

  const storeTokensAndNavigate = async (tokenData) => {
    const tokenStore = rememberMe ? localStorage : sessionStorage;
    const otherStore = rememberMe ? sessionStorage : localStorage;
    if (rememberMe) localStorage.setItem("sacco_remember_session", "true");
    else localStorage.removeItem("sacco_remember_session");
    otherStore.removeItem("access");
    otherStore.removeItem("refresh");
    tokenStore.setItem("access", tokenData.access);
    tokenStore.setItem("refresh", tokenData.refresh);

    if (rememberMe) localStorage.setItem("sacco_remember_username", username);
    else localStorage.removeItem("sacco_remember_username");

    const authenticatedUser = await refreshUser();
    if (!authenticatedUser) {
      setMessage(
        "Your sign-in was accepted, but we couldn't load your portal. Check your connection and refresh to retry."
      );
      return;
    }

    navigate(portalDestination(authenticatedUser), { replace: true });
  };

  const handleLoginError = (err) => {
    setAttempts((prev) => prev + 1);
    if (err.response?.status === 401 || err.response?.status === 400) {
      const msgs = [
        "Invalid username or password.",
        "Incorrect credentials. Please try again.",
        "Login failed. Check your username and password.",
      ];
      setMessage(msgs[Math.min(attempts, msgs.length - 1)]);
    } else if (err.response?.status === 429) {
      setMessage("Too many attempts. Please wait before trying again.");
    } else if (err.code === "ERR_NETWORK") {
      setMessage("Cannot connect to the SACCO server. Check your connection and try again.");
    } else {
      setMessage("Something went wrong. Please try again.");
    }
  };

  return (
    <>
      <PublicNavigation />
      <div className="auth-page">
      <div className="auth-card">
        {/* Brand header */}
        <div className="auth-brand" style={{ textAlign: "center", marginBottom: "28px" }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: "14px" }}>
            <SaccoLogo size={56} variant="dark" />
          </div>
          <h1 className="auth-title">{sacco.name}</h1>
          <p className="auth-subtitle">Member and staff access</p>
        </div>

        {!twoFaMode ? (
          <form className="auth-form" onSubmit={handleLogin} autoComplete="on">
            {/* Username */}
            <div className="auth-field">
              <label htmlFor="username">Username</label>
              <div className="auth-input-wrap">
                <span className="auth-input-icon"><Icon name="user" size={17} /></span>
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

            {/* Password */}
            <div className="auth-field">
              <label htmlFor="password">Password</label>
              <div className="auth-input-wrap">
                <span className="auth-input-icon"><Icon name="lock" size={17} /></span>
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete={rememberMe ? "current-password" : "off"}
                  className="auth-input-with-icon"
                  style={{ paddingRight: "48px" }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="auth-toggle-pw"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  <Icon name={showPassword ? "eyeOff" : "eye"} size={18} />
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

            {/* Public computer warning */}
            {!rememberMe && (
              <div style={{
                padding: "10px 14px", borderRadius: "8px", fontSize: "14px",
                background: "var(--color-warning-bg)", border: "1px solid var(--color-warning-border)", color: "var(--warning-text)",
                display: "flex", gap: "8px", alignItems: "flex-start",
              }}>
                <Icon name="lock" size={16} />
                <span>
                  <strong>Shared / public computer?</strong> Good — "Remember me" is off.
                  You will be automatically logged out after <strong>15 minutes</strong> of inactivity.
                  Always click <strong>Logout</strong> when done.
                </span>
              </div>
            )}

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
        ) : (
          <>
            <div className="auth-challenge-heading">
              <div className="auth-otp-icon"><Icon name="shield" size={30} /></div>
              <h2>Staff sign-in verification</h2>
              <p>Enter the 6-digit code for <strong>{twoFaInfo?.masked_destination}</strong>.</p>
            </div>
            <div
              className={`auth-challenge-message ${twoFaInfo?.delivery_status === "accepted" ? "info" : "error"}`}
              role={twoFaInfo?.delivery_status === "accepted" ? "status" : "alert"}
              aria-live="polite"
            >
              <Icon name={twoFaInfo?.delivery_status === "accepted" ? "check" : "alert"} size={17} />
              <span>{twoFaInfo?.message || "Staff verification is required before login can finish."}</span>
            </div>
            <form className="auth-form" onSubmit={handleVerify2FA} autoComplete="off">
              <div className="auth-field">
                <label htmlFor="otp">Verification code</label>
                <div className="auth-input-wrap">
                  <span className="auth-input-icon"><Icon name="lock" size={17} /></span>
                  <input
                    id="otp"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    placeholder="Enter 6-digit code"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                    required
                    autoFocus
                    className="auth-input-with-icon auth-login-otp"
                    autoComplete="one-time-code"
                  />
                </div>
              </div>

              <div className="auth-twofa-actions">
                <button className="auth-button" type="submit" disabled={loading || otp.length < 6}>
                  {loading ? <><span className="auth-spinner" /> Verifying…</> : "Verify and sign in"}
                </button>
                <button
                  className="auth-resend-button"
                  type="button"
                  onClick={handleResend2FA}
                  disabled={loading || resending || resendSeconds > 0}
                >
                  {resending ? "Requesting code…" : resendSeconds > 0 ? `Resend code in ${resendSeconds}s` : "Resend code"}
                </button>
                <button className="auth-secondary-button" type="button" onClick={backToSignIn} disabled={loading || resending}>
                  Back to sign in
                </button>
              </div>
            </form>
          </>
        )}

        {/* Error message */}
        {message && (
          <div className="auth-message error" role="alert">
            <Icon name="alert" size={18} /> {message}
          </div>
        )}

        {/* Security notice */}
        <div className="auth-security-notice">
          <Icon name="shield" size={16} />
          <span>Your connection is encrypted. Never share your password with anyone.</span>
        </div>

        {/* Register link */}
        <div className="auth-footer">
          Don't have an account?{" "}
          <Link to="/register">Register here</Link>
        </div>
      </div>

      {/* Footer */}
      <div className="auth-page-footer">
        © {new Date().getFullYear()} {sacco.name} · {sacco.address}
      </div>
      </div>
    </>
  );
}

export default Login;
