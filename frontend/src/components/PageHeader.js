import React from "react";
import buildingImage from "../assets/uphsl-building.png";

function PageHeader({ eyebrow, title, subtitle, supportingText, actions }) {
  return (
    <div className="app-page-header">
      <div className="app-page-header-copy">
        {eyebrow && <div className="app-eyebrow">{eyebrow}</div>}
        <h1 className="app-page-title">{title}</h1>
        {subtitle && <p className="app-page-subtitle">{subtitle}</p>}
        {supportingText && <div className="app-page-header-support">{supportingText}</div>}
      </div>
      <img className="app-page-header-building" src={buildingImage} alt="" aria-hidden="true" />
      {actions && <div className="app-page-actions">{actions}</div>}
    </div>
  );
}

export default PageHeader;
