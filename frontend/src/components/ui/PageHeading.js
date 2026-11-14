import React from "react";

export default function PageHeading({ title, description, actions, eyebrow }) {
  return (
    <header className="ui-page-heading">
      <div>
        {eyebrow && <p className="ui-eyebrow">{eyebrow}</p>}
        <h1 className="section-title">{title}</h1>
        {description && <p className="section-subtitle">{description}</p>}
      </div>
      {actions && <div className="ui-page-actions">{actions}</div>}
    </header>
  );
}
