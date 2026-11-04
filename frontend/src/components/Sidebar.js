import React from "react";
import logo from "../assets/uphsl_logo.png";

/**
 * Shared sidebar shell used by all three dashboards, matching the reference
 * design: brand header, icon-based nav items, user footer with avatar circle.
 *
 * items: [{ key, label, icon }] and optional section headings { group: "Plan" }
 */
function Sidebar({ brandLabel, workspaceLabel, items, activeKey, onSelect, userName, userRole, onSignOut }) {
  const initials = (userName || "?")
    .replace(/^(dr|mr|ms|mrs|engr|prof)\.?\s+/i, "")
    .split(/[\s-]+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="app-sidebar">
      <div className="app-sidebar-brand">
        <img src={logo} alt="UPHSL U-FAST logo" className="app-sidebar-logo-img" />
        <div>
          <div className="app-sidebar-brand-name">{brandLabel}</div>
          <div className="app-sidebar-brand-sub">{workspaceLabel}</div>
        </div>
      </div>

      <ul className="app-sidebar-nav">
        {items.map((item) => item.group ? (
          <li key={"g-" + item.group} className="app-nav-group">{item.group}</li>
        ) : (
          <li key={item.key}>
            <button
              className={activeKey === item.key ? "app-nav-item active" : "app-nav-item"}
              onClick={() => onSelect(item.key)}
            >
              <span className="app-nav-icon">{item.icon}</span>
              {item.label}
            </button>
          </li>
        ))}
      </ul>

      <div className="app-sidebar-user">
        <div className="app-avatar-circle">{initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="app-sidebar-user-name">{userName}</div>
          <div className="app-sidebar-user-role">{userRole}</div>
        </div>
      </div>
      <button className="app-sidebar-signout" onClick={onSignOut}>Sign out</button>
    </div>
  );
}

export default Sidebar;
