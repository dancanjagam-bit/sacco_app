import React from "react";
import Icon from "./Icon";

/** A primary balance card with clearly separated supporting account figures. */
export default function AccountCard({
  label,
  value,
  helper,
  icon = "wallet",
  loading = false,
  details = [],
  children,
  className = "",
}) {
  const classes = ["ui-account-card", className].filter(Boolean).join(" ");

  return (
    <section className={classes} aria-label={label}>
      <div className="ui-account-card-main">
        <div className="ui-account-card-heading">
          <div>
            <p className="ui-account-card-label">{label}</p>
            {helper && <p className="ui-account-card-helper">{helper}</p>}
          </div>
          <span className="ui-account-card-icon"><Icon name={icon} size={20} /></span>
        </div>
        <p className="ui-account-card-value" aria-live="polite">
          {loading ? "Loading…" : value ?? "Unavailable"}
        </p>
      </div>
      {details.length > 0 && (
        <dl className="ui-account-card-details">
          {details.map((detail) => (
            <div key={detail.label}>
              <dt>{detail.label}</dt>
              <dd>{detail.value ?? "Unavailable"}</dd>
            </div>
          ))}
        </dl>
      )}
      {children && <div className="ui-account-card-footer">{children}</div>}
    </section>
  );
}
