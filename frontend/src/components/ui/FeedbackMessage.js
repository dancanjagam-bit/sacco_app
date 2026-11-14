import React from "react";
import Icon from "./Icon";

export default function FeedbackMessage({ tone = "info", title, children, action, className = "" }) {
  const icon = tone === "success" ? "check" : tone === "warning" || tone === "danger" ? "alert" : "file";
  const classes = ["ui-feedback", "ui-feedback-" + tone, className].filter(Boolean).join(" ");
  return (
    <div className={classes} role={tone === "danger" ? "alert" : "status"}>
      <Icon name={icon} size={19} />
      <div className="ui-feedback-copy">
        {title && <strong>{title}</strong>}
        {children && <div>{children}</div>}
        {action && <div className="ui-feedback-action">{action}</div>}
      </div>
    </div>
  );
}
