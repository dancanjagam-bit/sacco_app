import React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function AuthRecovery() {
  const navigate = useNavigate();
  const { authError, refreshUser, logout, loading } = useAuth();

  const returnToLogin = async () => {
    await logout();
    navigate("/", { replace: true });
  };

  return (
    <main
      role="alert"
      style={{
        maxWidth: 520,
        margin: "12vh auto",
        padding: 28,
        border: "1px solid #f4c97a",
        borderRadius: 14,
        background: "#fffbeb",
        color: "#713f12",
        fontFamily: "inherit",
      }}
    >
      <h1 style={{ marginTop: 0, fontSize: 22 }}>Your session is saved</h1>
      <p>{authError || "We could not reconnect to your account."}</p>
      <p>Your account data will appear when the connection is restored.</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        <button type="button" onClick={refreshUser} disabled={loading}>
          {loading ? "Retrying…" : "Retry connection"}
        </button>
        <button type="button" onClick={returnToLogin}>
          Sign in with another account
        </button>
      </div>
    </main>
  );
}
