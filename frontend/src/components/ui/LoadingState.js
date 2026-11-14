import React from "react";

export default function LoadingState({ label = "Loading information…" }) {
  return (
    <div className="ui-loading" role="status">
      <span className="ui-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
