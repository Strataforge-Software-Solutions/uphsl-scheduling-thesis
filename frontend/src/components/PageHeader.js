import React from "react";

function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <div className="app-page-header">
      <div>
        {eyebrow && <div className="app-eyebrow">{eyebrow}</div>}
        <h1 className="app-page-title">{title}</h1>
        {subtitle && <p className="app-page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="app-page-actions">{actions}</div>}
    </div>
  );
}

export default PageHeader;
