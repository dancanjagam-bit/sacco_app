import React from "react";

const STATUS_LABELS = {
  requested: "Requested", pending: "Pending confirmation", uncertain: "Needs investigation",
  succeeded: "Paid", failed: "Failed", confirmed: "Confirmed", partial: "Partial",
  needs_review: "Needs review", upcoming: "Upcoming", overdue: "Overdue", paid: "Paid",
  approved: "Approved", rejected: "Rejected", active: "Active", cancelled: "Cancelled", posted: "Posted",
  scheduled: "Scheduled", ended: "Ended", closed: "Closed", available: "Available", inactive: "Inactive",
  former_owner: "Formerly owned", awaiting_journal: "Awaiting posting", unverified: "Awaiting confirmation",
  reversed: "Reversed", unmatched: "Unmatched", disputed: "Disputed", excess: "Excess",
};
const STATUS_TONES = {
  succeeded: "success", confirmed: "success", paid: "success", posted: "success", approved: "success", active: "success",
  failed: "danger", rejected: "danger", overdue: "danger",
  pending: "warning", requested: "warning", uncertain: "warning", partial: "warning", needs_review: "warning",
  awaiting_journal: "warning", unmatched: "warning", disputed: "warning", excess: "warning",
  upcoming: "neutral", cancelled: "neutral",
};

export default function StatusBadge({ status, label, className = "" }) {
  const key = String(status || "unknown").toLowerCase();
  const classes = ["ui-status", "ui-status-" + (STATUS_TONES[key] || "neutral"), className].filter(Boolean).join(" ");
  return (
    <span className={classes}>
      <span className="ui-status-dot" aria-hidden="true" />
      {label || STATUS_LABELS[key] || String(status || "Unavailable").replaceAll("_", " ")}
    </span>
  );
}
