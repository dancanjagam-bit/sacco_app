import React from "react";

/** Nairobi West transport cooperative mark, using the project's SVG variants. */
export default function SaccoLogo({ size = 48, variant = "color", showText = false }) {
  const lightMark = variant === "light" || variant === "white";
  const publicPath = (process.env.PUBLIC_URL || "").replace(/\/$/, "");
  const logoPath = `${publicPath}/nairobi-west-tuktuk-${lightMark ? "light" : "dark"}.svg`;
  const textColor = lightMark ? "#ffffff" : "#0f172a";

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: size * 0.22, flexShrink: 0 }}>
      <img
        src={logoPath}
        width={size}
        height={Math.round(size * 2 / 3)}
        alt="Nairobi West tuktuk"
        className="sacco-logo-image"
      />

      {/* ── Wordmark ── */}
      {showText && (
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
          <span style={{
            fontSize: size * 0.42,
            fontWeight: 900,
            letterSpacing: "0.08em",
            color: textColor,
            fontFamily: "'Inter', 'Segoe UI', sans-serif",
            textTransform: "uppercase",
          }}>
            SACCO
          </span>
          <span style={{
            fontSize: size * 0.19,
            fontWeight: 600,
            letterSpacing: "0.15em",
            color: variant === "white" ? "rgba(255,255,255,.6)" : "#64748b",
            fontFamily: "'Inter', 'Segoe UI', sans-serif",
            textTransform: "uppercase",
          }}>
            Transport Cooperative
          </span>
        </div>
      )}
    </div>
  );
}
