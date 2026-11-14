import React from "react";

/** Scrollable, labelled container used by financial tables. */
export default function DataTable({ label, children, className = "", tabIndex = 0 }) {
  return (
    <div
      className={["ui-table-wrap", className].filter(Boolean).join(" ")}
      role="region"
      aria-label={label}
      tabIndex={tabIndex}
    >
      {children}
    </div>
  );
}
