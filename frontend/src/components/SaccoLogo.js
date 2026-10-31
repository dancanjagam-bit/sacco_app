import React from "react";

/**
 * SACCO Premium Logo — SVG component
 * A geometric shield with an interlocking "S" monogram and wheat stalk detail.
 * Designed to evoke trust, growth, and financial strength — better than a stock bank eagle.
 *
 * Props:
 *  size      — number, controls width/height (default 48)
 *  variant   — "color" | "white" | "dark"  (default "color")
 *  showText  — bool, show "SACCO" wordmark beside the mark (default false)
 */
export default function SaccoLogo({ size = 48, variant = "color", showText = false }) {
  const primary   = variant === "white" ? "#fff" : "#4f46e5";
  const secondary = variant === "white" ? "rgba(255,255,255,.65)" : "#10b981";
  const accent    = variant === "white" ? "rgba(255,255,255,.35)" : "#f59e0b";
  const textColor = variant === "white" ? "#fff" : variant === "dark" ? "#0b1437" : "#1e1b4b";

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: size * 0.22, flexShrink: 0 }}>
      {/* ── The Mark ── */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-label="SACCO logo"
        role="img"
      >
        {/* Shield outer */}
        <path
          d="M32 4L8 14v16c0 15.5 10.5 27.8 24 32 13.5-4.2 24-16.5 24-32V14L32 4z"
          fill={primary}
          opacity="0.15"
        />
        {/* Shield inner fill */}
        <path
          d="M32 8L11 17v13c0 13.8 9.3 24.7 21 28.6C43.7 54.7 53 43.8 53 30V17L32 8z"
          fill={primary}
        />

        {/* Interlocking arc — top curve of S */}
        <path
          d="M24 26c0-4.4 3.6-8 8-8s8 3.6 8 8"
          stroke="#fff"
          strokeWidth="3.5"
          strokeLinecap="round"
          fill="none"
          opacity="0.95"
        />
        {/* Cross bar */}
        <line
          x1="24" y1="32"
          x2="40" y2="32"
          stroke="#fff"
          strokeWidth="3.5"
          strokeLinecap="round"
          opacity="0.9"
        />
        {/* Interlocking arc — bottom curve of S */}
        <path
          d="M40 38c0 4.4-3.6 8-8 8s-8-3.6-8-8"
          stroke={accent}
          strokeWidth="3.5"
          strokeLinecap="round"
          fill="none"
          opacity="0.95"
        />

        {/* Wheat stalk — left */}
        <path
          d="M22 48 Q18 42 20 36"
          stroke={secondary}
          strokeWidth="1.8"
          strokeLinecap="round"
          fill="none"
          opacity="0.8"
        />
        <ellipse cx="19" cy="34" rx="2.5" ry="1.5" fill={secondary} opacity="0.75" transform="rotate(-20 19 34)" />
        <ellipse cx="17.5" cy="38" rx="2.5" ry="1.5" fill={secondary} opacity="0.6" transform="rotate(-30 17.5 38)" />

        {/* Wheat stalk — right */}
        <path
          d="M42 48 Q46 42 44 36"
          stroke={secondary}
          strokeWidth="1.8"
          strokeLinecap="round"
          fill="none"
          opacity="0.8"
        />
        <ellipse cx="45" cy="34" rx="2.5" ry="1.5" fill={secondary} opacity="0.75" transform="rotate(20 45 34)" />
        <ellipse cx="46.5" cy="38" rx="2.5" ry="1.5" fill={secondary} opacity="0.6" transform="rotate(30 46.5 38)" />

        {/* Gold star accent — top */}
        <polygon
          points="32,6 33,9 36,9 33.5,11 34.5,14 32,12.5 29.5,14 30.5,11 28,9 31,9"
          fill={accent}
          opacity="0.85"
        />
      </svg>

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
            Management System
          </span>
        </div>
      )}
    </div>
  );
}
