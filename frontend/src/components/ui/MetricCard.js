import React from "react";
import Icon from "./Icon";

export default function MetricCard({ label, value, helper, icon = "bank", tone = "navy", loading = false }) {
  return (
    <section className={"ui-metric-card ui-metric-" + tone} aria-label={label}>
      <div className="ui-metric-head">
        <span className="ui-metric-label">{label}</span>
        <span className="ui-metric-icon"><Icon name={icon} size={19} /></span>
      </div>
      <p className="ui-metric-value" aria-live="polite">{loading ? "Loading…" : value ?? "Unavailable"}</p>
      {helper && <p className="ui-metric-helper">{helper}</p>}
    </section>
  );
}
