import React from "react";

const STATUS_CONFIG = {
  pending:  { label: "Pending",  bg: "#6c757d", color: "#fff" },
  verified: { label: "Verified", bg: "#198754", color: "#fff" },
  failed:   { label: "Failed",   bg: "#dc3545", color: "#fff" },
  flagged:  { label: "Flagged",  bg: "#fd7e14", color: "#fff" },
};

function VerificationStatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || { label: status || "Unknown", bg: "#adb5bd", color: "#fff" };
  return (
    <span
      style={{
        display: "inline-block", padding: "3px 10px", borderRadius: "12px",
        backgroundColor: config.bg, color: config.color,
        fontSize: "0.78rem", fontWeight: 600, letterSpacing: "0.02em", textTransform: "capitalize",
      }}
      aria-label={`Verification status: ${config.label}`}
    >
      {config.label}
    </span>
  );
}

export default VerificationStatusBadge;
