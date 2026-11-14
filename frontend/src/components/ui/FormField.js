import React from "react";

export default function FormField({ label, htmlFor, hint, error, success, children, className = "" }) {
  const hintId = htmlFor && hint ? `${htmlFor}-hint` : undefined;
  const errorId = htmlFor && error ? `${htmlFor}-error` : undefined;
  const successId = htmlFor && success ? `${htmlFor}-success` : undefined;
  const describedBy = [
    React.isValidElement(children) ? children.props["aria-describedby"] : null,
    hintId,
    errorId,
    successId,
  ].filter(Boolean).join(" ") || undefined;
  const control = React.isValidElement(children)
    ? React.cloneElement(children, {
      "aria-describedby": describedBy,
      "aria-invalid": error ? true : children.props["aria-invalid"],
      "data-valid": success && !error ? "true" : undefined,
    })
    : children;

  return (
    <div className={["ui-field", className].filter(Boolean).join(" ")}>
      {label && <label className="ui-label" htmlFor={htmlFor}>{label}</label>}
      {control}
      {hint && <span className="ui-muted" id={hintId}>{hint}</span>}
      {error && <span className="ui-field-error" id={errorId} role="alert">{error}</span>}
      {!error && success && <span className="ui-field-success" id={successId} role="status">{success}</span>}
    </div>
  );
}
